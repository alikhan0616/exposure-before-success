"""Tool registry: schemas out, calls in (SPEC §4).

A trial sees only the tools of its own environment -- inbox 3, calendar 3, web
search 2. The registry binds the environment argument so the model-visible
signature matches the published schema exactly, dispatches calls by name, and
produces the `tool_call_trace` records for the run log.

Nothing here raises on model error. An unknown tool name, a missing argument or
a tool-side failure all come back as an error payload the model can read: a
trial that dies on a malformed call tells us nothing about injection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable

from ..task_types import ToolCallRecord
from . import calendar_tools, inbox_tools, web_search_tools

# How much of a tool result is kept in the trace (SPEC §4: "result preview").
PREVIEW_CHARS = 240

# Which tools each environment exposes. This is the whole tool surface; SPEC §4
# calls the list final.
ENVIRONMENT_TOOLS: dict[str, tuple[str, ...]] = {
    "inbox": ("list_emails", "read_email", "send_email"),
    "calendar": ("view_calendar", "add_event", "delete_event"),
    "web_search": ("search_web", "fetch_page"),
}

# name -> unbound implementation (first parameter is the environment)
_IMPLEMENTATIONS: dict[str, Callable[..., Any]] = {
    "read_email": inbox_tools.read_email,
    "list_emails": inbox_tools.list_emails,
    "send_email": inbox_tools.send_email,
    "view_calendar": calendar_tools.view_calendar,
    "add_event": calendar_tools.add_event,
    "delete_event": calendar_tools.delete_event,
    "search_web": web_search_tools.search_web,
    "fetch_page": web_search_tools.fetch_page,
}

_SCHEMAS: dict[str, dict[str, Any]] = {
    schema["function"]["name"]: schema
    for module in (inbox_tools, calendar_tools, web_search_tools)
    for schema in module.TOOL_SCHEMAS
}


@dataclass
class ToolResult:
    """Outcome of one tool call."""

    name: str
    payload: Any  # JSON-serializable: dict, list or str
    record: ToolCallRecord
    ok: bool = True

    def as_message_content(self) -> str:
        """The tool result as the string sent back to the model."""
        return serialize(self.payload)


def serialize(payload: Any) -> str:
    """Render a tool payload as the text the model receives."""
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False)


def preview(payload: Any, limit: int = PREVIEW_CHARS) -> str:
    """Truncated rendering of a payload, for the trace."""
    text = serialize(payload)
    return text if len(text) <= limit else text[:limit] + "..."


class ToolRegistry:
    """The tools available to one trial, bound to that trial's environment."""

    def __init__(self, environment: str, env: Any) -> None:
        if environment not in ENVIRONMENT_TOOLS:
            known = ", ".join(sorted(ENVIRONMENT_TOOLS))
            raise KeyError(f"unknown environment {environment!r}; known: {known}")
        self.environment = environment
        self.env = env
        self.tool_names: tuple[str, ...] = ENVIRONMENT_TOOLS[environment]
        self._bound: dict[str, Callable[..., Any]] = {
            name: partial(_IMPLEMENTATIONS[name], env) for name in self.tool_names
        }

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """OpenAI-format function schemas for this environment's tools."""
        return [_SCHEMAS[name] for name in self.tool_names]

    def call(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """Execute one tool call and return its result plus a trace record."""
        args = dict(args or {})
        func = self._bound.get(name)

        if func is None:
            available = ", ".join(self.tool_names)
            payload: Any = {
                "error": f"No tool named {name!r}. Available tools: {available}"
            }
            return self._result(name, args, payload, ok=False)

        try:
            payload = func(**args)
        except TypeError as exc:  # wrong/missing arguments from the model
            payload = {"error": f"Invalid arguments for {name}: {exc}"}
            return self._result(name, args, payload, ok=False)
        except Exception as exc:  # tool-side failure; keep the trial alive
            payload = {"error": f"{name} failed: {type(exc).__name__}: {exc}"}
            return self._result(name, args, payload, ok=False)

        return self._result(name, args, payload, ok=True)

    def _result(self, name: str, args: dict[str, Any], payload: Any, ok: bool) -> ToolResult:
        record = ToolCallRecord(tool=name, args=args, result_preview=preview(payload))
        return ToolResult(name=name, payload=payload, record=record, ok=ok)


def build_registry(environment: str, env: Any) -> ToolRegistry:
    """Registry for `environment`, bound to `env`."""
    return ToolRegistry(environment, env)
