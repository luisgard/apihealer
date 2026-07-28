"""
LLM providers: the "brain" that generates the fix, pluggable.

The engine must not marry a specific provider. This defines a minimal interface
(LLMProvider) and one or more implementations. Switching from Claude to Azure
OpenAI, OpenAI or a local model is a matter of which implementation is
instantiated, without touching the adapter or the core.

No implementation embeds credentials in code: they read them from environment
variables. That way the repo can be public without leaking keys.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    ok: bool
    text: str
    error: str = ""


class LLMProvider(ABC):
    """Minimal contract: takes instructions + context, returns text."""

    name: str = "base"

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 2000) -> LLMResponse:
        """
        Send `system` (role/instructions) and `user` (the concrete task with the
        code and errors) to the model and return its response as text.

        It does not parse the result: interpreting the response (extracting the
        corrected code) is the caller's job, because that depends on the
        language adapter, not on the LLM provider.
        """
        raise NotImplementedError


class EnvConfiguredProvider(LLMProvider):
    """
    Handy base for providers configured via environment variables.
    Centralizes reading the API key so it isn't repeated.
    """

    #: Name of the environment variable holding the API key.
    api_key_env: str = ""

    def _get_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env)


def build_fix_prompt(
    language: str,
    breaking_changes: str,
    compiler_errors: str,
    code_context: str,
    related_context: str = "",
) -> tuple[str, str]:
    """
    Build (system, user) to request a fix. Lives here, next to the interface,
    because the prompt is common to any provider; only the transport differs.

    The key instruction: return ONLY the corrected code, with no explanations,
    so it can be applied programmatically. And don't make things up: if something
    can't be resolved with the given information, say so instead of guessing.

    `related_context` is optional smarter context: relevant type/DTO definitions
    or client signatures pulled from elsewhere in the project, so the model
    doesn't have to guess the shape of types it can't see in the target file.
    Giving the model the right surrounding context is often worth more than a
    bigger model.
    """
    system = (
        f"You are an assistant that fixes {language} code broken by an API "
        "contract change. You receive: the contract change, the compiler errors "
        "(which point exactly to what broke and where), the affected code, and "
        "optionally related type definitions for context. "
        "Return ONLY the complete corrected code of the file, with no "
        "explanations and no markdown fences. If you cannot resolve an error with "
        "certainty, do not invent: keep the original code for that part and add a "
        "TODO comment describing the doubt."
    )
    related_block = (
        f"\n# Related type/context (read-only, do not output):\n{related_context}\n"
        if related_context.strip()
        else ""
    )
    user = (
        f"# Detected contract change:\n{breaking_changes}\n\n"
        f"# Compiler errors:\n{compiler_errors}\n"
        + related_block
        + f"\n# Current code of the file to fix:\n{code_context}\n\n"
        "Return the complete corrected file."
    )
    return system, user
