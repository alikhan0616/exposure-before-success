"""Provider plumbing: parsing, retry, limiting, config, encoding (SPEC §7, §13).

Everything here is exercised only against live APIs otherwise, which is exactly
where it must not first be tested: the retry and rate-limit paths exist for the
free-tier failures that show up hours into a run. A fake HTTP client stands in
for the network.
"""

from __future__ import annotations

import logging
import sys
import time

import httpx
import pytest

from src.console import use_utf8_console, utf8_file_handler
from src.providers import (
    PROVIDERS,
    CerebrasProvider,
    GeminiProvider,
    GroqProvider,
    OpenRouterProvider,
)
from src.providers.base import (
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderError,
    RateLimiter,
    TokenRateLimiter,
    estimate_request_tokens,
    RetryPolicy,
    load_env_file,
    load_provider_config,
    read_env,
)

URDU = "براہ کرم یہ پیغام فوراً بھیجیں"


class FakeResponse:
    def __init__(self, status_code=200, body=None, text="", headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeClient:
    """Returns queued responses (or raises queued exceptions) in order."""

    def __init__(self, *queued):
        self.queued = list(queued)
        self.posts = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append({"url": url, "headers": headers, "json": json})
        item = self.queued.pop(0) if self.queued else FakeResponse()
        if isinstance(item, BaseException):
            raise item
        return item


def ok_body(text="hello", tool_calls=None):
    message = {"content": text}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


class StubProvider(OpenAICompatibleProvider):
    name = "groq"  # borrows a configured name; config is injected below anyway
    base_url = "https://stub.example/v1"
    api_key_env = "STUB_KEY"
    model_env = "STUB_MODEL"
    default_model = "stub-model"


def make_provider(client, max_attempts=3, rpm=0):
    return StubProvider(
        api_key="k",
        client=client,
        config=ProviderConfig(
            rpm=rpm,
            retry=RetryPolicy(
                max_attempts=max_attempts,
                initial_backoff_seconds=0.001,
                backoff_multiplier=2.0,
                max_backoff_seconds=0.01,
            ),
        ),
    )


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Backoff must not actually cost the test suite wall-clock time."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


# -- response parsing -------------------------------------------------------


def test_parses_text_and_stop_reason():
    provider = make_provider(FakeClient(FakeResponse(body=ok_body("hi"))))
    response = provider.chat([{"role": "user", "content": "x"}], [])

    assert response.message == "hi"
    assert response.stop_reason == "stop"
    assert response.has_tool_calls is False


def test_parses_tool_calls_with_json_arguments():
    body = ok_body(
        text="",
        tool_calls=[
            {
                "id": "c1",
                "function": {"name": "send_email", "arguments": '{"to": "a@b.example"}'},
            }
        ],
    )
    provider = make_provider(FakeClient(FakeResponse(body=body)))
    response = provider.chat([], [])

    assert response.has_tool_calls
    call = response.tool_calls[0]
    assert (call.id, call.name) == ("c1", "send_email")
    assert call.arguments == {"to": "a@b.example"}


def test_malformed_tool_arguments_do_not_raise():
    """A model that emits broken JSON still made a call (SPEC §4)."""
    body = ok_body(
        text="",
        tool_calls=[{"id": "c1", "function": {"name": "send_email", "arguments": "{not json"}}],
    )
    provider = make_provider(FakeClient(FakeResponse(body=body)))
    call = provider.chat([], []).tool_calls[0]

    assert call.name == "send_email"
    assert call.arguments["_raw_arguments"] == "{not json"


def test_null_content_becomes_empty_string():
    """Gemini's shim returns content=None on a tool-calls-only turn."""
    body = {"choices": [{"message": {"content": None}, "finish_reason": "tool_calls"}]}
    provider = make_provider(FakeClient(FakeResponse(body=body)))

    assert provider.chat([], []).message == ""


def test_response_without_choices_is_a_provider_error():
    provider = make_provider(FakeClient(FakeResponse(body={"error": {"message": "nope"}})))
    with pytest.raises(ProviderError, match="no choices"):
        provider.chat([], [])


def test_non_ascii_content_survives_parsing():
    provider = make_provider(FakeClient(FakeResponse(body=ok_body(URDU))))
    assert provider.chat([], []).message == URDU


# -- request shape ----------------------------------------------------------


def test_payload_carries_model_messages_and_tools():
    client = FakeClient(FakeResponse(body=ok_body()))
    provider = make_provider(client)
    schemas = [{"type": "function", "function": {"name": "list_emails"}}]
    provider.chat([{"role": "user", "content": "x"}], schemas)

    sent = client.posts[0]["json"]
    assert sent["model"] == "stub-model"
    assert sent["messages"] == [{"role": "user", "content": "x"}]
    assert sent["tools"] == schemas
    assert sent["tool_choice"] == "auto"
    assert client.posts[0]["url"] == "https://stub.example/v1/chat/completions"


def test_tool_keys_are_omitted_when_no_tools_are_offered():
    client = FakeClient(FakeResponse(body=ok_body()))
    make_provider(client).chat([], [])

    assert "tools" not in client.posts[0]["json"]
    assert "tool_choice" not in client.posts[0]["json"]


def test_api_key_travels_in_the_authorization_header():
    client = FakeClient(FakeResponse(body=ok_body()))
    make_provider(client).chat([], [])

    assert client.posts[0]["headers"]["Authorization"] == "Bearer k"


# -- retry policy (SPEC §7, §13) --------------------------------------------


def test_retryable_status_is_retried_then_succeeds():
    client = FakeClient(
        FakeResponse(status_code=429, text="slow down"),
        FakeResponse(status_code=503, text="unwell"),
        FakeResponse(body=ok_body("recovered")),
    )
    provider = make_provider(client, max_attempts=3)

    assert provider.chat([], []).message == "recovered"
    assert len(client.posts) == 3


def test_non_retryable_status_fails_on_the_first_attempt():
    """A bad key or unknown model must not burn five attempts."""
    client = FakeClient(FakeResponse(status_code=401, text="invalid api key"))
    provider = make_provider(client)

    with pytest.raises(ProviderError) as excinfo:
        provider.chat([], [])
    assert excinfo.value.status == 401
    assert len(client.posts) == 1


def test_gives_up_after_max_attempts():
    """SPEC §15: never retry forever -- the trial becomes an error row."""
    client = FakeClient(*[FakeResponse(status_code=429, text="rate limited")] * 4)
    provider = make_provider(client, max_attempts=4)

    with pytest.raises(ProviderError) as excinfo:
        provider.chat([], [])
    assert excinfo.value.attempts == 4
    assert excinfo.value.status == 429
    assert len(client.posts) == 4


def test_network_errors_are_retried():
    client = FakeClient(httpx.ConnectError("connection reset"), FakeResponse(body=ok_body("ok")))
    provider = make_provider(client)

    assert provider.chat([], []).message == "ok"
    assert len(client.posts) == 2


def test_backoff_is_exponential_and_capped():
    policy = RetryPolicy(
        initial_backoff_seconds=2, backoff_multiplier=2, max_backoff_seconds=60
    )
    delays = [policy.backoff_for(n) for n in range(1, 7)]

    assert delays[:5] == [2, 4, 8, 16, 32]
    assert delays[5] == 60  # capped, not 64


def test_retry_after_header_is_honoured_within_the_cap(monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    client = FakeClient(
        FakeResponse(status_code=429, text="wait", headers={"Retry-After": "5"}),
        FakeResponse(body=ok_body()),
    )
    provider = StubProvider(
        api_key="k",
        client=client,
        config=ProviderConfig(
            rpm=0,
            retry=RetryPolicy(
                max_attempts=2,
                initial_backoff_seconds=1,
                backoff_multiplier=2,
                max_backoff_seconds=30,
            ),
        ),
    )
    provider.chat([], [])

    assert slept == [5.0]


def test_absurd_retry_after_cannot_park_the_run(monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    client = FakeClient(
        FakeResponse(status_code=429, text="wait", headers={"Retry-After": "86400"}),
        FakeResponse(body=ok_body()),
    )
    provider = StubProvider(
        api_key="k",
        client=client,
        config=ProviderConfig(
            rpm=0,
            retry=RetryPolicy(max_attempts=2, max_backoff_seconds=30),
        ),
    )
    provider.chat([], [])

    assert slept == [30.0]


# -- rate limiting ----------------------------------------------------------


def test_limiter_allows_calls_up_to_the_cap():
    clock = [1000.0]
    limiter = RateLimiter(rpm=3, window_seconds=60)
    slept = []

    for _ in range(3):
        assert limiter.acquire(sleep=slept.append, now=lambda: clock[0]) == 0.0
    assert slept == []


def test_limiter_sleeps_once_the_window_is_full():
    clock = [1000.0]

    def now():
        return clock[0]

    def sleep(seconds):
        clock[0] += seconds

    limiter = RateLimiter(rpm=2, window_seconds=60)
    limiter.acquire(sleep=sleep, now=now)
    clock[0] += 10
    limiter.acquire(sleep=sleep, now=now)

    waited = limiter.acquire(sleep=sleep, now=now)
    assert waited == pytest.approx(50.0)  # until the first call leaves the window


def test_limiter_is_disabled_when_rpm_is_zero():
    limiter = RateLimiter(rpm=0)
    slept = []
    for _ in range(100):
        limiter.acquire(sleep=slept.append, now=lambda: 0.0)
    assert slept == []


# -- config (SPEC §7: caps in YAML, not code) -------------------------------


def test_groq_limits_are_verified():
    config = load_provider_config("groq")
    assert config.rpm == 30
    assert config.verified is True


def test_every_registered_provider_has_a_rate_limit_entry():
    """A provider with no cap would run uncapped against a free tier."""
    for name in PROVIDERS:
        assert load_provider_config(name).rpm > 0


def test_unknown_provider_config_raises():
    with pytest.raises(KeyError):
        load_provider_config("nonesuch")


# -- keys and model ids (SPEC §13) ------------------------------------------


def test_env_file_parsing_handles_comments_quotes_and_export(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        '# comment\nexport A=1\nB="two"\nC=\nnot_a_pair\nD=has=equals\n',
        encoding="utf-8",
    )
    values = load_env_file(path)

    assert values == {"A": "1", "B": "two", "C": "", "D": "has=equals"}


def test_missing_env_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "absent") == {}


def test_process_environment_wins_over_the_file(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "override-from-shell")
    assert read_env("GROQ_MODEL") == "override-from-shell"


def test_missing_key_fails_at_construction_not_mid_run():
    class KeylessProvider(StubProvider):
        api_key_env = "DEFINITELY_UNSET_KEY_a1b2"

    with pytest.raises(ValueError, match="missing API key"):
        KeylessProvider(config=ProviderConfig(rpm=0, retry=RetryPolicy()))


# -- the concrete providers (SPEC §7, plus Cerebras) ------------------------


def test_all_providers_are_registered():
    # SPEC §7's three, plus Cerebras -- added for its 1M tokens/day budget once
    # Groq's 200k/day became the binding constraint on diagnostic runs.
    assert set(PROVIDERS) == {"groq", "gemini", "cerebras", "openrouter"}


@pytest.mark.parametrize(
    "cls, host",
    [
        (GroqProvider, "api.groq.com"),
        (GeminiProvider, "generativelanguage.googleapis.com"),
        (OpenRouterProvider, "openrouter.ai"),
        (CerebrasProvider, "api.cerebras.ai"),
    ],
)
def test_endpoints_point_at_the_right_host(cls, host):
    assert host in cls.base_url
    assert cls.api_key_env.endswith("_API_KEY")


def test_openrouter_refuses_to_guess_a_model(monkeypatch):
    """§7: free-tier ids change; an unset model must fail, not default."""
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setattr("src.providers.base.load_env_file", lambda *a, **k: {})

    with pytest.raises(ValueError, match="no model set"):
        OpenRouterProvider(api_key="k", config=ProviderConfig(rpm=0, retry=RetryPolicy()))


def test_openrouter_sends_attribution_headers():
    client = FakeClient(FakeResponse(body=ok_body()))
    provider = OpenRouterProvider(
        model="vendor/model:free",
        api_key="k",
        client=client,
        config=ProviderConfig(rpm=0, retry=RetryPolicy()),
    )
    provider.chat([], [])

    assert client.posts[0]["headers"]["X-Title"] == "ipi-harness"


# -- encoding (SPEC §13 logging; Urdu/Roman Urdu everywhere) ----------------


def test_use_utf8_console_is_safe_under_captured_streams():
    use_utf8_console()  # pytest replaces sys.stdout with a non-reconfigurable stream
    use_utf8_console()  # and calling twice must stay harmless


def test_use_utf8_console_reconfigures_a_real_text_stream(monkeypatch):
    recorded = {}

    class Stream:
        def reconfigure(self, **kwargs):
            recorded.update(kwargs)

    monkeypatch.setattr(sys, "stdout", Stream())
    monkeypatch.setattr(sys, "stderr", Stream())
    use_utf8_console()

    assert recorded == {"encoding": "utf-8", "errors": "replace"}


def test_log_handler_writes_urdu_without_raising(tmp_path):
    """The §13 run log must survive the first Urdu payload it records."""
    path = tmp_path / "run.log"
    handler = utf8_file_handler(path)
    logger = logging.getLogger("test_urdu_log")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("injected_text=%s", URDU)
    finally:
        logger.removeHandler(handler)
        handler.close()

    assert URDU in path.read_text(encoding="utf-8")


def test_tool_call_extra_content_is_preserved():
    """Gemini 3.x returns a thought_signature here and 400s without it back."""
    signature = {"google": {"thought_signature": "abc123"}}
    body = ok_body(
        text="",
        tool_calls=[
            {
                "id": "c1",
                "extra_content": signature,
                "function": {"name": "list_emails", "arguments": "{}"},
            }
        ],
    )
    provider = make_provider(FakeClient(FakeResponse(body=body)))

    assert provider.chat([], []).tool_calls[0].extra_content == signature


def test_tool_call_without_extra_content_gets_an_empty_dict():
    body = ok_body(text="", tool_calls=[{"id": "c1", "function": {"name": "x", "arguments": "{}"}}])
    provider = make_provider(FakeClient(FakeResponse(body=body)))

    assert provider.chat([], []).tool_calls[0].extra_content == {}


# -- token-per-minute limiter (the free-tier binding constraint) ------------


def test_token_limiter_allows_requests_under_the_cap():
    clock = [0.0]
    lim = TokenRateLimiter(tpm=8000, window_seconds=60)
    slept = []
    for _ in range(3):
        s, h = lim.acquire(2000, sleep=slept.append, now=lambda: clock[0])
        assert s == 0.0 and h is not None
    assert slept == []  # 3 x 2000 = 6000 < 8000


def test_token_limiter_sleeps_when_a_request_would_exceed_tpm():
    clock = [0.0]
    def now(): return clock[0]
    def sleep(s): clock[0] += s
    lim = TokenRateLimiter(tpm=8000, window_seconds=60)

    lim.acquire(5000, sleep=sleep, now=now)
    slept, _ = lim.acquire(5000, sleep=sleep, now=now)  # 10000 > 8000

    assert slept == pytest.approx(60.0)  # waits for the first entry to age out


def test_reconcile_replaces_the_estimate_with_actual_usage():
    """Over-reserving then correcting frees budget for the next call."""
    clock = [0.0]
    lim = TokenRateLimiter(tpm=8000, window_seconds=60)
    _, handle = lim.acquire(7000, sleep=lambda s: None, now=lambda: clock[0])
    lim.reconcile(handle, 1000)  # the call really used 1000, not 7000

    # 1000 used + a 6000 request now fits without sleeping.
    slept, _ = lim.acquire(6000, sleep=lambda s: None, now=lambda: clock[0])
    assert slept == 0.0


def test_reconcile_zero_retires_a_rejected_request():
    """A 429 consumes no tokens; its reservation must not linger."""
    clock = [0.0]
    lim = TokenRateLimiter(tpm=8000, window_seconds=60)
    _, handle = lim.acquire(8000, sleep=lambda s: None, now=lambda: clock[0])
    lim.reconcile(handle, 0)

    slept, _ = lim.acquire(8000, sleep=lambda s: None, now=lambda: clock[0])
    assert slept == 0.0  # the retired reservation freed the whole window


def test_token_limiter_disabled_when_tpm_is_zero():
    lim = TokenRateLimiter(tpm=0)
    slept = []
    for _ in range(100):
        s, h = lim.acquire(999999, sleep=slept.append, now=lambda: 0.0)
        assert s == 0.0 and h is None
    assert slept == []


def test_a_request_bigger_than_the_whole_budget_is_not_a_deadlock():
    clock = [0.0]
    lim = TokenRateLimiter(tpm=8000, window_seconds=60)
    slept, h = lim.acquire(20000, sleep=lambda s: None, now=lambda: clock[0])
    assert slept == 0.0 and h is not None  # empty window -> allowed through


def test_effective_tpm_applies_the_safety_fraction():
    cfg = ProviderConfig(rpm=30, retry=RetryPolicy(), tpm=8000, token_safety_fraction=0.85)
    assert cfg.effective_tpm == 6800
    assert ProviderConfig(rpm=30, retry=RetryPolicy(), tpm=0).effective_tpm == 0


def test_groq_config_enforces_tokens_gemini_does_not():
    assert load_provider_config("groq").tpm == 8000
    assert load_provider_config("gemini").tpm == 0  # unverified -> limiter off


def test_token_estimate_grows_with_payload_and_reserves_output():
    small = estimate_request_tokens({"messages": [{"role": "user", "content": "hi"}]}, 0)
    big = estimate_request_tokens(
        {"messages": [{"role": "user", "content": "x" * 4000}], "tools": [{"a": "b" * 400}]}, 0
    )
    assert big > small
    assert estimate_request_tokens({"messages": []}, 1024) >= 1024


def test_provider_reconciles_token_usage_from_the_response():
    """End to end: a real response's usage.total_tokens lands in the window."""
    body = dict(ok_body("hi"))
    body["usage"] = {"total_tokens": 1234}
    client = FakeClient(FakeResponse(body=body))
    provider = StubProvider(
        api_key="k", client=client,
        config=ProviderConfig(rpm=0, retry=RetryPolicy(), tpm=8000),
    )
    provider.chat([{"role": "user", "content": "hi"}], [])

    used = sum(e[1] for e in provider.token_limiter._entries)
    assert used == 1234
