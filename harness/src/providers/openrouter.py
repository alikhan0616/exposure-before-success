"""OpenRouter via its OpenAI-compatible endpoint (SPEC §7).

The third provider. OpenRouter is a router rather than a lab: the model id is
`vendor/model`, and free-tier-eligible ids carry a `:free` suffix that can be
withdrawn without notice, so `OPENROUTER_MODEL` must be set explicitly in
`.env` -- there is no defensible hardcoded default (§7: "pick one that is
free-tier eligible", verified at build time).

`GET /api/v1/models` lists what the key can reach and what each id costs.
"""

from __future__ import annotations

from .base import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter free tier. RPM cap lives in `config/rate_limits.yaml`."""

    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    api_key_env = "OPENROUTER_API_KEY"
    model_env = "OPENROUTER_MODEL"
    # Deliberately empty: an unset model must fail loudly at construction
    # rather than silently route trials to whatever id happened to be pinned
    # here when the free tier changed.
    default_model = ""

    def headers(self) -> dict[str, str]:
        """Auth plus the attribution headers OpenRouter asks clients to send.

        They are optional, but they are how OpenRouter attributes free-tier
        traffic; sending them makes a quota question answerable later.
        """
        headers = super().headers()
        headers["HTTP-Referer"] = "https://github.com/ipi-urdu-project"
        headers["X-Title"] = "ipi-harness"
        return headers
