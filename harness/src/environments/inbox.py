"""Inbox environment state (SPEC §3.1).

State and mutation only: no tool logic, no scoring, no I/O beyond loading the
deterministic fixture.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Email:
    """One message sitting in the inbox."""

    id: str
    sender: str
    subject: str
    body: str
    timestamp: str  # ISO 8601, UTC


@dataclass
class SentEmail:
    """One outbound message. This list is what the exfiltration checkers read."""

    to: str
    subject: str
    body: str


@dataclass
class Inbox:
    """Mutable inbox state."""

    emails: list[Email] = field(default_factory=list)
    sent: list[SentEmail] = field(default_factory=list)

    @classmethod
    def from_fixture(cls, path: str | Path) -> "Inbox":
        """Build a fresh inbox from a seed file (SPEC §3, determinism).

        Every call re-reads the file and constructs new `Email` objects, so two
        instances never share mutable state and a trial can never leak into the
        next one.
        """
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        emails = [
            Email(
                id=rec["id"],
                sender=rec["sender"],
                subject=rec["subject"],
                body=rec["body"],
                timestamp=rec["timestamp"],
            )
            for rec in data["emails"]
        ]
        emails.sort(key=lambda e: (e.timestamp, e.id))
        return cls(emails=emails)

    def add_email(self, email: Email) -> None:
        """Append an email, keeping the list ordered oldest-first."""
        self.emails.append(email)
        self.emails.sort(key=lambda e: (e.timestamp, e.id))

    def get_email(self, email_id: str) -> Email | None:
        """The email with this id, or None."""
        for email in self.emails:
            if email.id == email_id:
                return email
        return None

    def list_emails(self) -> list[Email]:
        """All emails, oldest first."""
        return list(self.emails)

    def latest_email(self) -> Email | None:
        """The newest email -- the object the `easy` inbox task is about."""
        return self.emails[-1] if self.emails else None

    def record_sent(self, to: str, subject: str, body: str) -> SentEmail:
        """Record an outbound message and return the record."""
        record = SentEmail(to=to, subject=subject, body=body)
        self.sent.append(record)
        return record
