"""Attack-success checkers (SPEC §6)."""

from __future__ import annotations

from .checkers import (
    CHECKERS,
    check_add_malicious_event,
    check_delete_calendar_events,
    check_leak_contact_list,
    check_recommend_specific_product,
    check_send_email_to_attacker,
    get_checker,
)

__all__ = [
    "CHECKERS",
    "check_add_malicious_event",
    "check_delete_calendar_events",
    "check_leak_contact_list",
    "check_recommend_specific_product",
    "check_send_email_to_attacker",
    "get_checker",
]
