"""Environment state classes (SPEC §3).

One class per environment, each built from a deterministic fixture. A trial
gets a fresh instance and only ever touches the environment its UserTask names
(SPEC §10: never share state across trials).
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from .calendar import Calendar, Event, EventOp
from .inbox import Email, Inbox, SentEmail
from .web_search import Page, Query, SearchIndex

Environment = Union[Inbox, Calendar, SearchIndex]

_LOADERS = {
    "inbox": Inbox.from_fixture,
    "calendar": Calendar.from_fixture,
    "web_search": SearchIndex.from_fixture,
}


def make_environment(environment: str, fixture_path: str | Path) -> Environment:
    """Fresh environment of the named kind, seeded from `fixture_path`."""
    try:
        loader = _LOADERS[environment]
    except KeyError:
        known = ", ".join(sorted(_LOADERS))
        raise KeyError(f"unknown environment {environment!r}; known: {known}") from None
    return loader(fixture_path)


__all__ = [
    "Calendar",
    "Email",
    "Environment",
    "Event",
    "EventOp",
    "Inbox",
    "Page",
    "Query",
    "SearchIndex",
    "SentEmail",
    "make_environment",
]
