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
    infer: bool = False,
) -> tuple[str, str]:
    """
    Build (system, user) to request a fix. Lives here, next to the interface,
    because the prompt is common to any provider; only the transport differs.

    Two modes:
      - Compiler-driven (infer=False, generated clients): the compiler errors
        pinpoint exactly what broke, so the model corrects with certainty.
      - Inferred (infer=True, manual clients): there are no compiler errors to
        lean on, so the model makes a best-effort structural remediation from
        the contract diff -- creating new DTOs, renaming fields, updating usages --
        instead of leaving TODOs. It is told to APPLY its best inference, and to
        add a short comment only where a mapping is genuinely a guess. The
        honesty lives in the VerificationReport (level = inferred), not in
        refusing to act.

    Returning ONLY the corrected code keeps it programmatically applicable.

    `related_context` is optional smarter context: relevant type/DTO definitions
    or client signatures pulled from elsewhere in the project.
    """
    if infer:
        system = (
            f"You are an assistant that repairs {language} code broken by an API "
            "contract change, for a HAND-WRITTEN client where the compiler gives "
            "no signal. From the contract diff, make your best-effort structural "
            "remediation and APPLY it: create any new DTO classes the new shape "
            "implies, rename or renest fields to match, and update every usage so "
            "the code compiles against the new contract. Map removed fields to "
            "their most likely replacement by name, type and structure (e.g. a "
            "removed `customerId` and a new `customer.id` are almost certainly the "
            "same value renested). Do NOT leave the code unchanged and do NOT emit "
            "TODO-only stubs. Add a brief inline comment ONLY on a line whose "
            "mapping is a genuine guess. Return ONLY the complete updated code of "
            "the file, no explanations and no markdown fences."
        )
    else:
        system = (
            f"You are an assistant that fixes {language} code broken by an API "
            "contract change. You receive: the contract change, the compiler errors "
            "(which point exactly to what broke and where), the affected code, and "
            "optionally related type definitions for context. "
            "Return ONLY the complete corrected code of the file, with no "
            "explanations and no markdown fences. If you cannot resolve an error "
            "with certainty, do not invent: keep the original code for that part "
            "and add a TODO comment describing the doubt."
        )
    related_block = (
        f"\n# Related type/context (read-only, do not output):\n{related_context}\n"
        if related_context.strip()
        else ""
    )
    errors_label = "Compiler errors" if not infer else "No compiler errors (infer from the diff)"
    user = (
        f"# Detected contract change:\n{breaking_changes}\n\n"
        f"# {errors_label}:\n{compiler_errors}\n"
        + related_block
        + f"\n# Current code of the file to fix:\n{code_context}\n\n"
        "Return the complete corrected file."
    )
    return system, user
