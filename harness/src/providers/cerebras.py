"""Cerebras via its OpenAI-compatible endpoint (SPEC §7).

Added as a fourth provider when Groq's 200k tokens/day cap became the binding
constraint on diagnostics. Cerebras' free trial tier is the mirror image: a
much larger daily budget (1M tokens) behind a much tighter per-minute one
(5 requests/min, 30k input tokens/min), which suits a harness that already
throttles on both axes -- the run is slower but it finishes.

Model id comes from `CEREBRAS_MODEL`; `gpt-oss-120b` is the free-tier default
and supports tool calling. `GET /v1/models` lists what the key can reach.
"""

from __future__ import annotations

from .base import OpenAICompatibleProvider


class CerebrasProvider(OpenAICompatibleProvider):
    """Cerebras free trial tier. Limits live in `config/rate_limits.yaml`."""

    name = "cerebras"
    base_url = "https://api.cerebras.ai/v1"
    api_key_env = "CEREBRAS_API_KEY"
    model_env = "CEREBRAS_MODEL"
    default_model = "gpt-oss-120b"
