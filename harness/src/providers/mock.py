"""Scripted provider for tests and dry runs (SPEC §14 step 5).

`ScriptedProvider` replays a fixed sequence of turns, so `agent_loop` can be
exercised end to end -- tool calls, tool results, final message, checkers --
without spending a single free-tier request. It also records every `chat()`
argument, which is how the smoke test asserts that tool results are fed back in
the right shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .base import Provider, ProviderError, ProviderResponse, ToolCall


def tool_turn(name: str, arguments: dict[str, Any] | None = None, *, call_id: str = "") -> ProviderResponse:
    """A turn in which the model calls one tool and says nothing."""
    return ProviderResponse(
        message="",
        tool_calls=[ToolCall(id=call_id or f"call_{name}", name=name, arguments=dict(arguments or {}))],
        stop_reason="tool_calls",
    )


def text_turn(message: str) -> ProviderResponse:
    """A final turn: assistant text, no tool calls."""
    return ProviderResponse(message=message, stop_reason="stop")


@dataclass
class ScriptedProvider(Provider):
    """Returns `script[i]` on the i-th `chat()` call.

    A script entry may be a `ProviderResponse`, a plain string (shorthand for a
    final text turn), an exception instance (raised, to exercise the error
    path), or a callable taking `(messages, tools)` for turns that need to see
    what the loop sent.

    Running past the end of the script raises rather than looping: a silent
    repeat would let a runaway agent loop pass its own test.
    """

    script: list[Any] = field(default_factory=list)
    name: str = "mock"
    model: str = "scripted"

    calls: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __init__(
        self,
        script: Iterable[Any] | None = None,
        *,
        name: str = "mock",
        model: str = "scripted",
    ) -> None:
        self.script = list(script or [])
        self.name = name
        self.model = model
        self.calls = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ProviderResponse:
        index = len(self.calls)
        self.calls.append({"messages": list(messages), "tools": list(tools), "kwargs": kwargs})

        if index >= len(self.script):
            raise ProviderError(
                f"{self.name}: script exhausted after {len(self.script)} turn(s); "
                "the loop asked for one more"
            )

        turn = self.script[index]
        if isinstance(turn, BaseException):
            raise turn
        if callable(turn) and not isinstance(turn, ProviderResponse):
            turn = turn(messages, tools)
        if isinstance(turn, str):
            return text_turn(turn)
        if not isinstance(turn, ProviderResponse):
            raise TypeError(f"{self.name}: script entry {index} is not a ProviderResponse: {turn!r}")
        return turn


def always(response: ProviderResponse | str) -> Callable[[list, list], ProviderResponse]:
    """Script helper: a turn that ignores what it was sent."""
    fixed = text_turn(response) if isinstance(response, str) else response
    return lambda _messages, _tools: fixed
