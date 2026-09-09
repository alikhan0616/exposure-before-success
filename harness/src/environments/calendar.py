"""Calendar environment state (SPEC §3.2).

State and mutation only. Date filtering resolves against the harness's pinned
date (SPEC-adjacent: `task_types.HARNESS_TODAY`), never the real system clock,
so "this week" means the same week on every run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..task_types import HARNESS_TODAY


@dataclass
class Event:
    """One calendar entry."""

    id: str
    title: str
    start_time: str  # ISO 8601, UTC
    end_time: str
    location: str
    description: str
    attendees: list[str] = field(default_factory=list)


@dataclass
class EventOp:
    """One mutation of the calendar. The calendar checkers read this log.

    `snapshot` holds the event's fields as they were at the moment of the op, so
    a delete can still be checked against the title of what was deleted.
    """

    op: str  # "add" | "delete" | "modify"
    event_id: str
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class Calendar:
    """Mutable calendar state."""

    events: list[Event] = field(default_factory=list)
    event_log: list[EventOp] = field(default_factory=list)
    today: str = HARNESS_TODAY  # pinned; see module docstring

    @classmethod
    def from_fixture(cls, path: str | Path) -> "Calendar":
        """Build a fresh calendar from a seed file (SPEC §3, determinism).

        Fixture loading is *not* an `add` op: `event_log` starts empty so the
        checkers only ever see mutations the model actually caused.
        """
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        events = [
            Event(
                id=rec["id"],
                title=rec["title"],
                start_time=rec["start_time"],
                end_time=rec["end_time"],
                location=rec["location"],
                description=rec["description"],
                attendees=list(rec["attendees"]),
            )
            for rec in data["events"]
        ]
        events.sort(key=lambda e: (e.start_time, e.id))
        return cls(events=events)

    # -- reads ------------------------------------------------------------

    def list_events(self, start_date: str | None = None, end_date: str | None = None) -> list[Event]:
        """Events whose start date falls in [start_date, end_date] (inclusive).

        Bounds are `YYYY-MM-DD` strings; either may be None for an open end.
        Comparison is on the date prefix of `start_time`, which is safe because
        every fixture timestamp is UTC ISO 8601.
        """
        out = []
        for ev in self.events:
            day = ev.start_time[:10]
            if start_date is not None and day < start_date:
                continue
            if end_date is not None and day > end_date:
                continue
            out.append(ev)
        return out

    def get_event(self, event_id: str) -> Event | None:
        """The event with this id, or None."""
        for ev in self.events:
            if ev.id == event_id:
                return ev
        return None

    def resolve_range(self, date_range: str | None) -> tuple[str | None, str | None]:
        """Turn a model-supplied date range into (start_date, end_date).

        Understands None / "all", "today", "tomorrow", "yesterday", "this week",
        "next week", a bare `YYYY-MM-DD`, and `YYYY-MM-DD..YYYY-MM-DD`.
        Anything else falls back to the open range: an unparseable filter must
        not hide the calendar from the model and derail the benign task.
        """
        if date_range is None:
            return (None, None)
        text = date_range.strip().lower()
        today = date.fromisoformat(self.today)

        if text in ("", "all", "any", "everything"):
            return (None, None)
        if text == "today":
            return (self.today, self.today)
        if text == "tomorrow":
            day = today + timedelta(days=1)
            return (day.isoformat(), day.isoformat())
        if text == "yesterday":
            day = today - timedelta(days=1)
            return (day.isoformat(), day.isoformat())
        if text in ("this week", "current week", "week"):
            monday = today - timedelta(days=today.isoweekday() - 1)
            return (monday.isoformat(), (monday + timedelta(days=6)).isoformat())
        if text == "next week":
            monday = today - timedelta(days=today.isoweekday() - 1) + timedelta(days=7)
            return (monday.isoformat(), (monday + timedelta(days=6)).isoformat())

        if ".." in text:
            first, _, second = text.partition("..")
            if _is_iso_date(first.strip()) and _is_iso_date(second.strip()):
                return (first.strip(), second.strip())
        if _is_iso_date(text):
            return (text, text)
        return (None, None)

    # -- mutations --------------------------------------------------------

    def add_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: list[str] | None = None,
        event_id: str | None = None,
    ) -> Event:
        """Add an event, log the op, and return it."""
        event = Event(
            id=event_id or self._next_event_id(),
            title=title,
            start_time=start_time,
            end_time=end_time,
            location=location,
            description=description,
            attendees=list(attendees or []),
        )
        self.events.append(event)
        self.events.sort(key=lambda e: (e.start_time, e.id))
        self.event_log.append(EventOp(op="add", event_id=event.id, snapshot=_snapshot(event)))
        return event

    def delete_event(self, event_id: str) -> Event | None:
        """Delete an event, log the op with a snapshot, return what was deleted."""
        event = self.get_event(event_id)
        if event is None:
            return None
        self.events.remove(event)
        self.event_log.append(EventOp(op="delete", event_id=event_id, snapshot=_snapshot(event)))
        return event

    def modify_event(self, event_id: str, **changes: Any) -> Event | None:
        """Apply field changes to an event, log the op, return the event."""
        event = self.get_event(event_id)
        if event is None:
            return None
        for key, value in changes.items():
            if hasattr(event, key) and key != "id":
                setattr(event, key, value)
        self.events.sort(key=lambda e: (e.start_time, e.id))
        self.event_log.append(EventOp(op="modify", event_id=event_id, snapshot=_snapshot(event)))
        return event

    def _next_event_id(self) -> str:
        """Deterministic id for a model-created event: c101, c102, ..."""
        n = 101 + sum(1 for op in self.event_log if op.op == "add")
        return f"c{n}"


def _snapshot(event: Event) -> dict[str, Any]:
    """The event's fields, detached from the live object."""
    return {
        "id": event.id,
        "title": event.title,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "location": event.location,
        "description": event.description,
        "attendees": list(event.attendees),
    }


def _is_iso_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False
