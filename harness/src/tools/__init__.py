"""Model-facing tools (SPEC §4).

Import the registry rather than the tool functions directly: it is what binds a
tool to a trial's environment and limits the surface to that environment's own
tools.
"""

from __future__ import annotations

from .registry import (
    ENVIRONMENT_TOOLS,
    ToolRegistry,
    ToolResult,
    build_registry,
    preview,
    serialize,
)

__all__ = [
    "ENVIRONMENT_TOOLS",
    "ToolRegistry",
    "ToolResult",
    "build_registry",
    "preview",
    "serialize",
]
