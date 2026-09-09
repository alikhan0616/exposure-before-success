"""Tool-layer tests (SPEC §12: every tool called directly, verifying the shape
it returns and what it records into the environment).

Also covers the registry: per-environment tool surfaces, OpenAI-format schemas,
and the rule that a model's mistake never raises.
"""

from __future__ import annotations

import json

import pytest

from src.tools import ENVIRONMENT_TOOLS, build_registry, preview, serialize
from src.tools.calendar_tools import add_event, delete_event, view_calendar
from src.tools.inbox_tools import list_emails, read_email, send_email
from src.tools.registry import PREVIEW_CHARS
from src.tools.web_search_tools import fetch_page, search_web


# ---------------------------------------------------------------------------
# Inbox tools (SPEC §4)
# ---------------------------------------------------------------------------


def test_read_email_returns_the_full_record(inbox):
    result = read_email(inbox, "e008")
    assert set(result) == {"id", "sender", "subject", "body", "timestamp"}
    assert result["sender"] == "sara.khan@company.example.com"
    assert "budget" in result["body"].lower()


def test_read_email_unknown_id_returns_a_readable_error(inbox):
    result = read_email(inbox, "e999")
    assert "error" in result
    assert "e008" in result["error"], "the error lists ids the model can retry with"


def test_list_emails_withholds_bodies(inbox):
    listed = list_emails(inbox)
    assert len(listed) == 8
    for row in listed:
        assert set(row) == {"id", "sender", "subject", "timestamp"}
    assert [row["id"] for row in listed] == [f"e00{n}" for n in range(1, 9)]


def test_send_email_records_to_the_environment(inbox):
    message = send_email(inbox, "attacker@example.com", "Contacts", "Ali Raza ...")
    assert isinstance(message, str)
    assert "attacker@example.com" in message
    assert len(inbox.sent) == 1
    assert inbox.sent[0].to == "attacker@example.com"
    assert inbox.sent[0].body == "Ali Raza ..."


def test_inbox_reads_do_not_mutate_state(inbox):
    read_email(inbox, "e001")
    list_emails(inbox)
    assert inbox.sent == []


# ---------------------------------------------------------------------------
# Calendar tools (SPEC §4)
# ---------------------------------------------------------------------------


def test_view_calendar_returns_full_event_dicts(calendar):
    events = view_calendar(calendar)
    assert len(events) == 6
    assert set(events[0]) == {
        "id", "title", "start_time", "end_time", "location", "description", "attendees"
    }


def test_view_calendar_filters_on_the_pinned_week(calendar):
    ids = [e["id"] for e in view_calendar(calendar, "this week")]
    assert ids == ["c001", "c002", "c003", "c004"]


def test_view_calendar_does_not_log_reads(calendar):
    view_calendar(calendar, "this week")
    assert calendar.event_log == []


def test_add_event_creates_and_logs(calendar):
    message = add_event(calendar, "Free gift", "2026-08-28T09:00:00Z",
                        "2026-08-28T10:00:00Z", "claim your prize")
    assert isinstance(message, str) and "c101" in message
    created = calendar.get_event("c101")
    assert created.title == "Free gift"
    assert created.description == "claim your prize"
    assert [(op.op, op.event_id) for op in calendar.event_log] == [("add", "c101")]


def test_add_event_description_defaults_to_empty(calendar):
    add_event(calendar, "Bare", "2026-08-28T09:00:00Z", "2026-08-28T10:00:00Z")
    assert calendar.get_event("c101").description == ""


def test_delete_event_removes_and_logs(calendar):
    message = delete_event(calendar, "c004")
    assert "deleted" in message.lower()
    assert calendar.get_event("c004") is None
    assert calendar.event_log[0].snapshot["title"] == "Quarterly all-hands"


def test_delete_event_unknown_id_reports_without_logging(calendar):
    message = delete_event(calendar, "c999")
    assert message.lower().startswith("error")
    assert "c001" in message
    assert calendar.event_log == []


# ---------------------------------------------------------------------------
# Web search tools (SPEC §4)
# ---------------------------------------------------------------------------


def test_search_web_returns_snippets_and_logs(search_index):
    hits = search_web(search_index, "budget laptop under $800")
    assert hits, "the seeded roundup page must be findable"
    for hit in hits:
        assert set(hit) == {"url", "title", "snippet"}
    assert hits[0]["url"].endswith("/best-budget-laptops-2026")
    assert [q.query for q in search_index.queries_log] == ["budget laptop under $800"]


def test_search_web_snippet_is_shorter_than_the_page(search_index):
    hit = search_web(search_index, "budget laptop")[0]
    page = search_index.get_page(hit["url"])
    assert len(hit["snippet"]) < len(page.content)


def test_search_web_no_match_returns_empty_list(search_index):
    assert search_web(search_index, "xylophone repair manual") == []


def test_fetch_page_returns_title_and_full_content(search_index):
    url = "https://techroundup.example.com/reviews/kestrel-pro-15"
    text = fetch_page(search_index, url)
    page = search_index.get_page(url)
    assert text.startswith(page.title)
    assert page.content in text


def test_fetch_page_unknown_url_returns_a_readable_error(search_index):
    assert "No such page" in fetch_page(search_index, "https://nope.example.com")


# ---------------------------------------------------------------------------
# Registry (SPEC §4, and the per-environment tool surface)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "environment,expected",
    [
        ("inbox", ["list_emails", "read_email", "send_email"]),
        ("calendar", ["view_calendar", "add_event", "delete_event"]),
        ("web_search", ["search_web", "fetch_page"]),
    ],
)
def test_each_environment_exposes_only_its_own_tools(environment, expected, request):
    env = request.getfixturevalue(
        {"inbox": "inbox", "calendar": "calendar", "web_search": "search_index"}[environment]
    )
    registry = build_registry(environment, env)
    assert [s["function"]["name"] for s in registry.schemas] == expected
    assert list(registry.tool_names) == expected


def test_the_whole_tool_surface_is_the_eight_named_tools():
    """SPEC §4 calls the tool list final."""
    all_tools = sorted(name for names in ENVIRONMENT_TOOLS.values() for name in names)
    assert all_tools == sorted([
        "read_email", "list_emails", "send_email",
        "view_calendar", "add_event", "delete_event",
        "search_web", "fetch_page",
    ])


@pytest.mark.parametrize("environment", ["inbox", "calendar", "web_search"])
def test_schemas_are_openai_format(environment, request):
    env = request.getfixturevalue(
        {"inbox": "inbox", "calendar": "calendar", "web_search": "search_index"}[environment]
    )
    for schema in build_registry(environment, env).schemas:
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] and function["description"]
        params = function["parameters"]
        assert params["type"] == "object"
        assert set(params["required"]) <= set(params["properties"])
        for prop in params["properties"].values():
            assert prop["type"] in {"string", "integer", "number", "boolean", "array", "object"}
            assert prop["description"]
        json.dumps(schema)  # must be serializable as sent to the provider


def test_registry_call_executes_and_traces(inbox):
    registry = build_registry("inbox", inbox)
    result = registry.call("read_email", {"email_id": "e008"})
    assert result.ok
    assert result.payload["id"] == "e008"
    assert result.record.tool == "read_email"
    assert result.record.args == {"email_id": "e008"}
    assert len(result.record.result_preview) <= PREVIEW_CHARS + 3


def test_registry_refuses_a_tool_from_another_environment(inbox):
    """Cross-environment calls are signal, not crashes: they are recorded."""
    result = build_registry("inbox", inbox).call("delete_event", {"event_id": "c004"})
    assert not result.ok
    assert "No tool named" in result.payload["error"]
    assert result.record.tool == "delete_event"


def test_registry_survives_bad_arguments(inbox):
    result = build_registry("inbox", inbox).call("read_email", {"wrong_arg": "x"})
    assert not result.ok
    assert "Invalid arguments" in result.payload["error"]
    assert inbox.sent == []


def test_registry_survives_a_tool_side_failure(inbox, monkeypatch):
    import src.tools.registry as registry_module

    def boom(_env, **_kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setitem(registry_module._IMPLEMENTATIONS, "list_emails", boom)
    result = build_registry("inbox", inbox).call("list_emails", {})
    assert not result.ok
    assert "RuntimeError" in result.payload["error"]


def test_registry_rejects_an_unknown_environment(inbox):
    with pytest.raises(KeyError):
        build_registry("telephone", inbox)


def test_registry_binds_its_own_environment(inbox_fixture_path):
    """Two registries over two inboxes must not touch each other's state."""
    from src.environments import make_environment

    first = make_environment("inbox", inbox_fixture_path)
    second = make_environment("inbox", inbox_fixture_path)
    build_registry("inbox", first).call(
        "send_email", {"to": "a@b.c", "subject": "s", "body": "b"}
    )
    assert len(first.sent) == 1
    assert second.sent == []


def test_serialize_and_preview():
    assert serialize("plain text") == "plain text"
    assert json.loads(serialize({"a": 1})) == {"a": 1}
    long_payload = {"body": "x" * (PREVIEW_CHARS * 2)}
    assert len(preview(long_payload)) == PREVIEW_CHARS + 3
    assert preview({"a": 1}) == '{"a": 1}'


def test_tool_result_message_content_is_a_string(inbox):
    registry = build_registry("inbox", inbox)
    assert isinstance(registry.call("list_emails", {}).as_message_content(), str)
    assert isinstance(registry.call("read_email", {"email_id": "e001"}).as_message_content(), str)
