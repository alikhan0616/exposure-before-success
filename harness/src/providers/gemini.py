"""Gemini provider via Google's OpenAI-compatible endpoint (SPEC §7).

Model id and key come from `.env` (`GEMINI_MODEL`, `GEMINI_API_KEY`) so swapping
models is a one-line change and no key is ever committed (§13).

Both ids §7 names -- `gemini-2.5-flash` and `gemini-2.5-flash-lite` -- were
already closed to new keys by 2026-08-28: they still appear in `GET /models`
but every completion returns 404 "no longer available to new users". Checked
live that day, `gemini-3.5-flash-lite` (default) and `gemini-flash-lite-latest`
both answer with tool calls. The default pins an explicit version rather than
the floating `-latest` alias, because a model that changes under the harness
would silently break the comparability of ASR numbers gathered across days.
"""

from __future__ import annotations

from .base import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    """Gemini free tier over the OpenAI shim. RPM cap in `config/rate_limits.yaml`."""

    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    api_key_env = "GEMINI_API_KEY"
    model_env = "GEMINI_MODEL"
    default_model = "gemini-3.5-flash-lite"
