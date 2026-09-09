"""Groq via its OpenAI-compatible endpoint (SPEC §7).

Groq is the first provider wired up end to end (SPEC §14 step 5: whichever key
works first), so it is the one the Day 3 checkpoint trial runs against.

Model id comes from `GROQ_MODEL`; Groq retires hosted models on short notice
(`llama-3.3-70b-versatile` was already gone by 2026-08-28), so swapping one is
an `.env` edit, never a code change. `GET /openai/v1/models` lists what the key
can actually reach -- check it before a full run. Verified tool-calling on this
account 2026-08-28: `openai/gpt-oss-20b` (default), `openai/gpt-oss-120b`,
`qwen/qwen3.8-27b`.
"""

from __future__ import annotations

from .base import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    """Groq free tier. RPM cap lives in `config/rate_limits.yaml`."""

    name = "groq"
    base_url = "https://api.groq.com/openai/v1"
    api_key_env = "GROQ_API_KEY"
    model_env = "GROQ_MODEL"
    default_model = "openai/gpt-oss-20b"
