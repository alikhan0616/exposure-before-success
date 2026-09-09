"""Inbox tools (SPEC §4).

Each function takes the environment first; `registry.py` binds that argument so
the model only ever sees the remaining parameters. Return values are plain
serializable dicts/strings. Failures are returned as text the model can read
and recover from, never raised -- an exception would end the trial and lose the
attack signal we are trying to measure.
"""

from __future__ import annotations

from typing import Any

from ..environments.inbox import Inbox


def read_email(inbox: Inbox, email_id: str) -> dict[str, Any]:
    """Read one email in full, including its body."""
    email = inbox.get_email(email_id)
    if email is None:
        known = ", ".join(e.id for e in inbox.emails)
        return {"error": f"No email with id {email_id!r}. Available ids: {known}"}
    return {
        "id": email.id,
        "sender": email.sender,
        "subject": email.subject,
        "body": email.body,
        "timestamp": email.timestamp,
    }


def list_emails(inbox: Inbox) -> list[dict[str, Any]]:
    """List every email as id/sender/subject/timestamp, newest last (SPEC §4: no bodies)."""
    return [
        {
            "id": email.id,
            "sender": email.sender,
            "subject": email.subject,
            "timestamp": email.timestamp,
        }
        for email in inbox.list_emails()
    ]


def send_email(inbox: Inbox, to: str, subject: str, body: str) -> str:
    """Send an email on the user's behalf; recorded in `Inbox.sent`."""
    inbox.record_sent(to=to, subject=subject, body=body)
    return f"Email sent to {to} with subject {subject!r}."


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "Read the full contents of one email, including its body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email_id": {
                        "type": "string",
                        "description": "Id of the email to read, e.g. 'e008'.",
                    }
                },
                "required": ["email_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_emails",
            "description": (
                "List the emails in the inbox with their id, sender, subject and "
                "timestamp, oldest first. Bodies are not included."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email from the user's account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Subject line."},
                    "body": {"type": "string", "description": "Body text of the email."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]
