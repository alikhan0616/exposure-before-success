"""Provider interface, rate limiting and retry policy (SPEC §7, §13).

All three planned providers (Gemini, Groq, OpenRouter) expose OpenAI-compatible
chat-completions endpoints, so the request and response shapes are identical
and only the base URL, key env var and model id differ. That shared work lives
in `OpenAICompatibleProvider` here; each concrete module is then a few lines of
configuration.

Two policies are enforced on every call, both read from
`config/rate_limits.yaml` rather than hardcoded (§7):

* a client-side rolling-window limiter that sleeps rather than tripping the
  provider's RPM cap, and
* bounded retry on 429/5xx/network errors -- exponential backoff, capped, with
  a hard attempt limit. After that the call raises `ProviderError`, which the
  agent loop records as an `error` row so the run continues (§13, §15).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "rate_limits.yaml"
ENV_PATH = REPO_ROOT / ".env"

logger = logging.getLogger(__name__)

# Read timeout for one chat completion. Long enough for a slow free-tier
# response, short enough that a hung connection cannot stall a 1,100-trial run.
REQUEST_TIMEOUT_SECONDS = 120

# Statuses worth retrying: the provider is rate limiting us or is briefly
# unwell. Everything else (401, 400, 404) is a configuration bug that retrying
# would only hide.
RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class ProviderError(RuntimeError):
    """A provider call failed and is not worth retrying further.

    Carries `status` when the failure came back as an HTTP response, so callers
    can tell a quota wall from a malformed request in the run log.
    """

    def __init__(self, message: str, *, status: int | None = None, attempts: int = 1) -> None:
        super().__init__(message)
        self.status = status
        self.attempts = attempts


# ---------------------------------------------------------------------------
# Response shapes (SPEC §7)
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """One tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]
    # Opaque provider-specific data attached to this call, echoed back verbatim
    # on the next turn. Gemini 3.x puts a `thought_signature` here and rejects
    # the follow-up request with HTTP 400 if it does not come back, which ends
    # every multi-step trial before the second tool call. Kept generic rather
    # than named after Gemini: it is the same shape any provider would use.
    extra_content: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Normalized provider reply: assistant text, tool calls, stop reason, raw."""

    message: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "stop"
    raw: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


# ---------------------------------------------------------------------------
# Config (SPEC §7: caps live in YAML, not in code)
# ---------------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Bounded exponential backoff (SPEC §7, §13)."""

    max_attempts: int = 5
    initial_backoff_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0

    def backoff_for(self, attempt: int) -> float:
        """Seconds to wait after `attempt` (1-based) has failed."""
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)


@dataclass
class ProviderConfig:
    """Everything `config/rate_limits.yaml` says about one provider."""

    rpm: int
    retry: RetryPolicy
    window_seconds: float = 60.0
    # Tokens-per-minute cap. 0 disables the token limiter (mock, tests, or a
    # provider whose tpm we have not verified).
    tpm: int = 0
    # Fraction of `tpm` the token limiter actually spends, as headroom.
    token_safety_fraction: float = 0.85
    # `true` once the caps were checked against the provider's live limits, an
    # ISO date string if the config records one instead, `None` if unchecked.
    verified: bool | str | None = None

    @property
    def effective_tpm(self) -> int:
        """The token budget the limiter enforces: tpm minus safety headroom."""
        if self.tpm <= 0:
            return 0
        return max(1, int(self.tpm * self.token_safety_fraction))


def load_provider_config(name: str, path: str | Path = CONFIG_PATH) -> ProviderConfig:
    """Read one provider's limits from the YAML config.

    An unknown provider is an error rather than a silent default: running
    uncapped against a free tier burns the quota the whole experiment needs.
    """
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    providers = raw.get("providers") or {}
    if name not in providers:
        known = ", ".join(sorted(providers)) or "(none)"
        raise KeyError(f"no rate-limit config for provider {name!r}; configured: {known}")
    entry = providers[name] or {}

    retry_raw = raw.get("retry") or {}
    retry = RetryPolicy(
        max_attempts=int(retry_raw.get("max_attempts", 5)),
        initial_backoff_seconds=float(retry_raw.get("initial_backoff_seconds", 2)),
        backoff_multiplier=float(retry_raw.get("backoff_multiplier", 2)),
        max_backoff_seconds=float(retry_raw.get("max_backoff_seconds", 60)),
    )
    limiter_raw = raw.get("rate_limiter") or {}

    return ProviderConfig(
        rpm=int(entry.get("rpm", 0)),
        retry=retry,
        window_seconds=float(limiter_raw.get("window_seconds", 60)),
        tpm=int(entry.get("tpm", 0)),
        token_safety_fraction=float(limiter_raw.get("token_safety_fraction", 0.85)),
        verified=entry.get("verified"),
    )


# ---------------------------------------------------------------------------
# Keys and model ids (SPEC §13: never hardcoded, never committed)
# ---------------------------------------------------------------------------


def load_env_file(path: str | Path = ENV_PATH) -> dict[str, str]:
    """Parse a `.env` file into a dict.

    Deliberately not a dependency: the file is `KEY=value` lines, optionally
    `export`-prefixed and optionally quoted, with `#` comments. Anything more
    exotic belongs in the shell environment, which wins anyway (`read_env`).
    """
    path = Path(path)
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        if key:
            values[key] = value.strip().strip("\"'")
    return values


def read_env(name: str, default: str | None = None) -> str | None:
    """A variable from the process environment, falling back to `.env`.

    The shell wins over the file, so a one-off
    `GROQ_MODEL=... python -m src.run_experiments` overrides the checked-in
    default without editing anything.
    """
    if name in os.environ:
        return os.environ[name]
    return load_env_file().get(name, default)


# ---------------------------------------------------------------------------
# Client-side rate limiting
# ---------------------------------------------------------------------------


class RateLimiter:
    """Rolling-window limiter: at most `rpm` acquisitions per window.

    Keeps the timestamps of recent calls and, when the window is full, sleeps
    until the oldest one falls out of it. `rpm <= 0` disables limiting, which is
    what the mock provider and tests want.
    """

    def __init__(self, rpm: int, window_seconds: float = 60.0) -> None:
        self.rpm = rpm
        self.window_seconds = window_seconds
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, sleep=time.sleep, now=time.monotonic) -> float:
        """Block until another call is allowed. Returns seconds slept."""
        if self.rpm <= 0:
            return 0.0

        with self._lock:
            current = now()
            self._expire(current)
            if len(self._calls) < self.rpm:
                self._calls.append(current)
                return 0.0
            wait = self._calls[0] + self.window_seconds - current

        if wait > 0:
            logger.info(
                "rate limiter sleeping %.1fs (cap %d/%.0fs)",
                wait, self.rpm, self.window_seconds,
            )
            sleep(wait)

        with self._lock:
            current = now()
            self._expire(current)
            self._calls.append(current)
        return max(wait, 0.0)

    def _expire(self, current: float) -> None:
        cutoff = current - self.window_seconds
        while self._calls and self._calls[0] <= cutoff:
            self._calls.popleft()


class TokenRateLimiter:
    """Rolling-window limiter on *tokens*, not requests.

    The request limiter above caps how many calls we make per minute; it cannot
    see how large each call is. On Groq's free tier the binding limit is
    tokens-per-minute (8000), and a single trial call -- full tool schemas plus
    a growing message list -- is 1-2.5k tokens, so an rpm-only limiter sails
    straight past the token cap and earns a 429. This limiter keeps a rolling
    60s sum of token cost and sleeps before a request that would exceed `tpm`.

    Costs are reserved with a pre-request estimate, then reconciled to the exact
    `usage.total_tokens` the response reports, so the running window converges on
    truth. `tpm <= 0` disables it (the mock provider and tests).
    """

    def __init__(self, tpm: int, window_seconds: float = 60.0) -> None:
        self.tpm = tpm
        self.window_seconds = window_seconds
        # each entry is a mutable [timestamp, tokens] so it can be reconciled.
        self._entries: deque[list[float]] = deque()
        self._lock = threading.Lock()

    def acquire(
        self, estimated_tokens: int, sleep=time.sleep, now=time.monotonic
    ) -> tuple[float, list[float] | None]:
        """Block until `estimated_tokens` fit under `tpm`. Returns (slept, handle).

        The handle is passed to `reconcile` once the real token count is known.
        A request larger than the whole per-minute budget is allowed through
        once the window is empty, rather than deadlocking forever.
        """
        if self.tpm <= 0:
            return 0.0, None
        est = max(1, int(estimated_tokens))
        slept = 0.0
        while True:
            with self._lock:
                current = now()
                self._expire(current)
                used = sum(e[1] for e in self._entries)
                if used + est <= self.tpm or not self._entries:
                    entry: list[float] = [current, float(est)]
                    self._entries.append(entry)
                    return slept, entry
                # Sleep until enough of the oldest tokens age out to fit `est`.
                need = used + est - self.tpm
                freed = 0.0
                wait_until = current + self.window_seconds
                for ts, tok in self._entries:
                    freed += tok
                    if freed >= need:
                        wait_until = ts + self.window_seconds
                        break
                wait = max(wait_until - current, 0.05)
            logger.info(
                "token limiter sleeping %.1fs (need %d tok, cap %d/%.0fs)",
                wait, est, self.tpm, self.window_seconds,
            )
            sleep(wait)
            slept += wait

    def reconcile(self, handle: list[float] | None, actual_tokens: int | None) -> None:
        """Replace an entry's estimate with the tokens the request really used.

        `actual_tokens=0` retires a request that consumed nothing -- a 429 is
        rejected before the model runs, so it must not keep weighing on the
        window and starving later calls.
        """
        if self.tpm <= 0 or handle is None or actual_tokens is None:
            return
        with self._lock:
            handle[1] = float(max(0, int(actual_tokens)))

    def _expire(self, current: float) -> None:
        cutoff = current - self.window_seconds
        while self._entries and self._entries[0][0] <= cutoff:
            self._entries.popleft()


def estimate_request_tokens(payload: dict[str, Any], output_reserve: int = 0) -> int:
    """Rough token cost of one request, for the token limiter's reservation.

    Deliberately an over-estimate: ~3.5 chars/token (real English is nearer 4,
    but the tool-schema JSON is denser), plus a reservation for the output the
    model may generate. Reserving high keeps us under the cap; the post-response
    `reconcile` then corrects the window to the exact count, so the over-estimate
    only briefly holds extra budget.
    """
    import json as _json

    text = _json.dumps(payload.get("messages", []), ensure_ascii=False)
    text += _json.dumps(payload.get("tools", []), ensure_ascii=False)
    return int(len(text) / 3.5) + 8 + max(0, int(output_reserve))


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


class Provider(ABC):
    """One model behind one endpoint (SPEC §7)."""

    name: str
    model: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ProviderResponse:
        """One completion turn. Raises `ProviderError` when retries are spent."""

    def __repr__(self) -> str:  # shows up in logs and progress lines
        return f"{type(self).__name__}(name={self.name!r}, model={self.model!r})"


class OpenAICompatibleProvider(Provider):
    """Shared client for any `/chat/completions` endpoint.

    Subclasses supply the base URL, the API-key env var and the default model;
    everything below -- limiting, retry, parsing -- is identical across them,
    which is the whole reason §7 specifies the OpenAI-compatible endpoints.
    """

    base_url: str = ""
    api_key_env: str = ""
    model_env: str = ""
    default_model: str = ""

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        config: ProviderConfig | None = None,
        client: httpx.Client | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = 1024,
    ) -> None:
        self.model = model or read_env(self.model_env) or self.default_model
        if not self.model:
            raise ValueError(f"{self.name}: no model set (pass model= or set {self.model_env})")

        self.api_key = api_key or read_env(self.api_key_env) or ""
        if not self.api_key:
            raise ValueError(
                f"{self.name}: missing API key -- set {self.api_key_env} in .env (SPEC §13)"
            )

        self.config = config or load_provider_config(self.name)
        self.limiter = RateLimiter(self.config.rpm, self.config.window_seconds)
        # Token-per-minute limiter: the binding free-tier constraint (see
        # rate_limits.yaml). Enforces tpm minus a safety fraction; 0 disables.
        self.token_limiter = TokenRateLimiter(
            self.config.effective_tpm, self.config.window_seconds
        )
        self.client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        # Greedy decoding by default: repeat runs should vary only by whatever
        # non-determinism the provider itself has (SPEC §3 determinism note).
        self.temperature = temperature
        self.max_tokens = max_tokens

    # -- request ------------------------------------------------------------

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", self.temperature),
        }
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = kwargs.pop("tool_choice", "auto")
        payload.update(kwargs)
        return payload

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ProviderResponse:
        payload = self.build_payload(messages, tools, **kwargs)
        retry = self.config.retry
        last_error = "no attempts made"
        last_status: int | None = None
        # Reserve the output ceiling too: the model may generate up to max_tokens,
        # and those count against tpm. Over-reserving is corrected by reconcile.
        estimate = estimate_request_tokens(payload, output_reserve=self.max_tokens or 0)

        for attempt in range(1, retry.max_attempts + 1):
            self.limiter.acquire()
            _slept, token_handle = self.token_limiter.acquire(estimate)
            response = None
            try:
                response = self.client.post(
                    self.endpoint,
                    headers=self.headers(),
                    json=payload,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except httpx.HTTPError as exc:  # network-level failure
                last_error = f"{type(exc).__name__}: {exc}"
                last_status = None
                self.token_limiter.reconcile(token_handle, 0)  # nothing consumed
            else:
                if response.status_code < 400:
                    body = response.json()
                    usage = (body.get("usage") or {}).get("total_tokens")
                    self.token_limiter.reconcile(
                        token_handle, usage if usage is not None else estimate
                    )
                    return self.parse_response(body)
                last_status = response.status_code
                last_error = f"HTTP {response.status_code}: {response.text[:400]}"
                # A 429 is rejected before the model runs, so it costs no tokens;
                # retire the reservation so it does not starve later calls.
                self.token_limiter.reconcile(token_handle, 0)
                if response.status_code not in RETRYABLE_STATUSES:
                    raise ProviderError(
                        f"{self.name}: {last_error}", status=last_status, attempts=attempt
                    )

            if attempt == retry.max_attempts:
                break
            delay = self._retry_delay(retry, attempt, response)
            logger.warning(
                "%s attempt %d/%d failed (%s); retrying in %.0fs",
                self.name, attempt, retry.max_attempts, last_error, delay,
            )
            time.sleep(delay)

        raise ProviderError(
            f"{self.name}: giving up after {retry.max_attempts} attempts -- {last_error}",
            status=last_status,
            attempts=retry.max_attempts,
        )

    def _retry_delay(self, retry: RetryPolicy, attempt: int, response: Any) -> float:
        """Backoff for the next attempt, honouring `Retry-After` when sane.

        A provider that tells us exactly how long to wait is worth listening to
        -- but only up to the configured cap, so a buggy header cannot park the
        run for an hour.
        """
        delay = retry.backoff_for(attempt)
        headers = getattr(response, "headers", None) or {}
        raw = headers.get("Retry-After")
        if raw:
            try:
                return min(max(float(raw), delay), retry.max_backoff_seconds)
            except (TypeError, ValueError):
                pass
        return delay

    # -- response -----------------------------------------------------------

    def parse_response(self, data: dict[str, Any]) -> ProviderResponse:
        """OpenAI-format response -> `ProviderResponse`."""
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.name}: response had no choices: {str(data)[:300]}")
        choice = choices[0]
        message = choice.get("message") or {}

        return ProviderResponse(
            message=message.get("content") or "",
            tool_calls=[self._parse_tool_call(tc) for tc in (message.get("tool_calls") or [])],
            stop_reason=choice.get("finish_reason") or "stop",
            raw=data,
        )

    @staticmethod
    def _parse_tool_call(raw: dict[str, Any]) -> ToolCall:
        """One `tool_calls` entry -> `ToolCall`, with arguments decoded.

        Malformed argument JSON is kept as a `_raw_arguments` string rather than
        raised: the registry turns a bad call into an error the model can read,
        and a trial that died here would lose its attack signal.
        """
        function = raw.get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, dict):
            parsed: Any = arguments
        else:
            try:
                parsed = json.loads(arguments or "{}")
            except (TypeError, ValueError):
                parsed = {"_raw_arguments": arguments}
        if not isinstance(parsed, dict):
            parsed = {"_raw_arguments": arguments}

        return ToolCall(
            id=raw.get("id") or "",
            name=function.get("name") or "",
            arguments=parsed,
            extra_content=raw.get("extra_content") or {},
        )
