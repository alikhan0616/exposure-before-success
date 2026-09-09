"""Calendar tools (SPEC §4).

Relative date ranges resolve against the calendar's pinned `today`
(`task_types.HARNESS_TODAY`), never the real system clock.
"""

from __future__ import annotations

from typing import Any

from ..environments.calendar import Calendar, Event


def _as_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "title": event.title,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "location": event.location,
        "description": event.description,
        "attendees": list(event.attendees),
    }


def view_calendar(calendar: Calendar, date_range: str | None = None) -> list[dict[str, Any]]:
    """List events, optionally narrowed to a date range."""
    start, end = calendar.resolve_range(date_range)
    return [_as_dict(ev) for ev in calendar.list_events(start, end)]


def add_event(
    calendar: Calendar,
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
) -> str:
    """Create a calendar event; recorded as an `add` op in `event_log`."""
    event = calendar.add_event(
        title=title, start_time=start_time, end_time=end_time, description=description
    )
    return f"Event {event.id} created: {event.title} at {event.start_time}."


def delete_event(calendar: Calendar, event_id: str) -> str:
    """Delete a calendar event; recorded as a `delete` op in `event_log`."""
    deleted = calendar.delete_event(event_id)
    if deleted is None:
        known = ", ".join(ev.id for ev in calendar.events)
        return f"Error: no event with id {event_id!r}. Available ids: {known}"
    return f"Event {event_id} deleted: {deleted.title}."


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "view_calendar",
            "description": "List the user's calendar events, optionally within a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_range": {
                        "type": "string",
                        "description": (
                            "Optional range filter. Accepts 'today', 'tomorrow', "
                            "'this week', 'next week', a single date as YYYY-MM-DD, "
                            "or a span as YYYY-MM-DD..YYYY-MM-DD. Omit for all events."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "Add a new event to the user's calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start_time": {
                        "type": "string",
                        "description": "Start time, ISO 8601, e.g. '2026-08-28T09:00:00Z'.",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time, ISO 8601.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description.",
                    },
                },
                "required": ["title", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Delete an event from the user's calendar by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Id of the event to delete, e.g. 'c004'.",
                    }
                },
                "required": ["event_id"],
            },
        },
    },
]
