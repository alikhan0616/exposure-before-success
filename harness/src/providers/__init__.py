"""Model providers (SPEC §7).

`build_provider("groq")` is the only entry point the orchestrator needs; the
registry below is what `--providers` on the CLI validates against.
"""

from __future__ import annotations

from typing import Any

from .base import (
    OpenAICompatibleProvider,
    Provider,
    ProviderConfig,
    ProviderError,
    ProviderResponse,
    RateLimiter,
    TokenRateLimiter,
    RetryPolicy,
    ToolCall,
    load_provider_config,
    read_env,
)
from .cerebras import CerebrasProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .openrouter import OpenRouterProvider

# SPEC §7's three, plus Cerebras (added for its 1M/day budget when Groq's
# 200k/day became the binding constraint). Ordered by how far each is verified:
# Groq, Gemini and Cerebras have answered real tool-calling requests on this
# key; OpenRouter is wired but unverified until its key and model are set.
PROVIDERS: dict[str, type[Provider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "cerebras": CerebrasProvider,
    "openrouter": OpenRouterProvider,
}


def build_provider(name: str, **kwargs: Any) -> Provider:
    """Instantiate a provider by name, failing loudly on an unknown one."""
    try:
        cls = PROVIDERS[name]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise KeyError(f"unknown provider {name!r}; known: {known}") from None
    return cls(**kwargs)


__all__ = [
    "CerebrasProvider",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "PROVIDERS",
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "ProviderResponse",
    "RateLimiter",
    "TokenRateLimiter",
    "RetryPolicy",
    "GroqProvider",
    "OpenRouterProvider",
    "ToolCall",
    "build_provider",
    "load_env_file",
    "load_provider_config",
    "read_env",
]
