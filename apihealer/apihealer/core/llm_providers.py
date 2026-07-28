"""
Concrete LLMProvider implementations and a factory that picks which to use.

ClaudeProvider is included as a reference implementation. Adding Azure OpenAI,
OpenAI or a local model is writing another class with the same `complete`
method and registering it in `get_provider`.

They all read credentials from environment variables; never from code.
Only the standard library (urllib) is used to avoid imposing dependencies; if
you prefer the official SDKs, replace the body of `complete` without changing
the interface.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .llm import EnvConfiguredProvider, LLMProvider, LLMResponse


class ClaudeProvider(EnvConfiguredProvider):
    """Reference provider: Anthropic messages API."""

    name = "claude"
    api_key_env = "ANTHROPIC_API_KEY"
    endpoint = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> LLMResponse:
        key = self._get_key()
        if not key:
            return LLMResponse(
                ok=False, text="",
                error=f"Missing environment variable {self.api_key_env}.",
            )
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                body = json.loads(resp.read())
            # The response carries a list of blocks; join the text ones.
            parts = [b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"]
            return LLMResponse(ok=True, text="".join(parts).strip())
        except Exception as exc:
            return LLMResponse(ok=False, text="", error=str(exc))


class OllamaProvider(LLMProvider):
    """
    LOCAL provider via Ollama (http://localhost:11434).

    Key advantage for this project: the user's code NEVER leaves their machine.
    To remediate internal repos, running the LLM locally is often almost a
    security requirement, not just a convenience.

    The default model is gemma4, but it's configurable: since the compiler
    verifies the fix, a modest local model is viable for localized changes
    (renaming a field, adjusting a type). For complex changes, prefer a stronger
    coding model (e.g. qwen3, gpt-oss); switch it with APIHEALER_LLM_MODEL
    without touching code.
    """

    name = "ollama"
    endpoint = "http://localhost:11434/api/chat"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("APIHEALER_LLM_MODEL", "gemma4")

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> LLMResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
                body = json.loads(resp.read())
            text = (body.get("message", {}) or {}).get("content", "")
            return LLMResponse(ok=True, text=text.strip())
        except Exception as exc:
            return LLMResponse(
                ok=False, text="",
                error=(
                    f"{exc}. Is Ollama running? Try 'ollama serve' and "
                    f"'ollama pull {self.model}'."
                ),
            )


# --- Factory ------------------------------------------------------------------

# Registry of available providers by name.
_PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "ollama": OllamaProvider,
    # "azure-openai": AzureOpenAIProvider,   # <- add here when it exists
    # "openai": OpenAIProvider,
}


def get_provider(name: str | None = None) -> LLMProvider | None:
    """
    Return the requested provider, or the one set by the APIHEALER_LLM
    environment variable, or None if none is configured.

    Designed to be "swappable without touching code": you pick the provider by
    configuration, not by editing the adapter.
    """
    chosen = (name or os.environ.get("APIHEALER_LLM", "")).strip().lower()
    if not chosen:
        return None
    provider_cls = _PROVIDERS.get(chosen)
    if provider_cls is None:
        return None
    return provider_cls()


def available_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())
