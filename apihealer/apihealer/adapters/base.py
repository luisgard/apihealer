"""
Contract every language adapter must fulfill.

The core only knows this interface, never the details of a specific language.
To support a new language, write a class that inherits from LanguageAdapter and
register it in adapters/__init__.py.

No method here executes the user's project code directly: concrete adapters
delegate to the language's native tools (e.g. nswag, dotnet, npm) by invoking
them as external processes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ClientKind(Enum):
    """
    How the project consumes the API. Part of the base contract so the CLI and
    the core can reason about any adapter without reflection.

    UNKNOWN is the default for adapters that don't implement a fine-grained
    classification yet; that way the base method can return something sensible.
    """
    GENERATED = "generated"  # regenerable client (NSwag/Kiota/openapi-generator)
    MANUAL = "manual"        # consumes API but no generator: hand-written / Refit
    NONE = "none"            # doesn't consume API: nothing to do
    UNKNOWN = "unknown"      # the adapter doesn't classify (contract default)


@dataclass
class ClientClassification:
    """
    Rich result of classifying a project, instead of a bare ClientKind.

    Carries not just the verdict but the EVIDENCE behind it, which is the whole
    point of APIHealer: being able to say *with what level of evidence* a
    decision was made. Also lets the CLI explain itself and the strategies
    reuse what the classifier already discovered (generator, candidate files)
    without re-scanning.

    - kind: the verdict (GENERATED / MANUAL / NONE / UNKNOWN).
    - confidence: 0.0 to 1.0 in the classification itself (not in the fix).
    - reasons: human-readable signals that led to the verdict.
    - generator_name: for GENERATED, which generator was detected (if any).
    - candidate_files: for MANUAL, files that appear to consume the API.
    """
    kind: ClientKind
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    generator_name: str | None = None
    candidate_files: list[str] = field(default_factory=list)


class VerificationKind(Enum):
    """
    How the proposed fix was (or wasn't) verified. Makes confidence explainable:
    a 0.5 backed by compilation is not the same as an unverified one.
    """
    BUILD = "build"                # recompiled and passed: the fix fits (generated case)
    INFERRED_BUILD = "inferred_build"  # manual: inferred a change, applied it, and it compiles
    BUILD_FAILED = "build_failed"  # recompiled and did NOT pass
    SYNTAX_ONLY = "syntax_only"    # compiled, but doesn't guarantee the contract (manual)
    NONE = "none"                  # couldn't verify (missing toolchain, etc.)


@dataclass
class VerificationReport:
    """
    Structured evidence behind a remediation -- the product's core differentiator,
    made data instead of prose.

    Rather than leaving "what can still be wrong" in the README, every result
    carries it explicitly, so a generated PR (or any downstream consumer) can
    list the residual risks a human must still check.

    - level: the kind of verification achieved (see VerificationKind).
    - evidence: what was actually checked (e.g. "recompiled and passed").
    - remaining_risks: what a passing verification does NOT prove, in this case.
    """
    level: VerificationKind = VerificationKind.NONE
    evidence: list[str] = field(default_factory=list)
    remaining_risks: list[str] = field(default_factory=list)


@dataclass
class RemediationResult:
    """
    Result of attempting to remediate a breaking change.

    Named a "result", not a "proposal", because it carries more than a
    suggestion: the changes, the evidence, the confidence and the residual
    risks. `applied` and `verification` are DELIBERATELY INDEPENDENT axes:
      - applied: did we WRITE changes to disk? (a side-effect fact)
      - verification: what EVIDENCE do we have that the fix is correct?
        (an epistemic fact, carried in a VerificationReport)
    A change can be applied but unverified (manual client that compiles), or
    verified without being "applied" in the business sense. Keeping them apart
    is the core of APIHealer's job: reporting the level of evidence honestly
    rather than conflating "I wrote it" with "I know it's right".

    - files_changed: paths (relative to the project) modified or proposed.
    - summary: human-readable description of what was done, for the PR body.
    - confidence: 0.0 to 1.0. The core uses this to decide whether to open a
      normal PR, mark it as draft, or stop and only warn.
    - applied: True if the change was written to disk; False if only proposed.
    - verification: structured evidence report (level + evidence + risks).
    - notes: warnings or things the human reviewer should look at carefully.
    """
    files_changed: list[str] = field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    confidence_factors: list[str] = field(default_factory=list)
    applied: bool = False
    verification: VerificationReport = field(default_factory=VerificationReport)
    notes: list[str] = field(default_factory=list)


# Backwards-compatible alias: the type was called FixProposal in earlier drafts.
FixProposal = RemediationResult


# Standard residual-risk phrasing per verification level, so every strategy
# reports the same honest limits without repeating the text.
_RISKS_BUILD = [
    "Runtime serialization behavior not exercised.",
    "Business logic / validation semantics not checked.",
    "New enum values or nullability changes may alter behavior.",
]
_RISKS_INFERRED = [
    "The field mapping was INFERRED from the contract diff, not proven.",
    "Compilation confirms types and references, not that the mapping is semantically right.",
    "Runtime behavior and validations not checked.",
]
_RISKS_SYNTAX_ONLY = [
    "Compilation only proves syntax, not contract semantics.",
    "A manual mapping can compile and still be wrong.",
    "Runtime behavior and validations not checked.",
]
_RISKS_NONE = [
    "No verification was possible; treat as unproven.",
]


def verification_report(level: VerificationKind, evidence: list[str] | None = None) -> "VerificationReport":
    """Build a VerificationReport with the standard residual risks for `level`."""
    risks = {
        VerificationKind.BUILD: _RISKS_BUILD,
        VerificationKind.INFERRED_BUILD: _RISKS_INFERRED,
        VerificationKind.SYNTAX_ONLY: _RISKS_SYNTAX_ONLY,
        VerificationKind.BUILD_FAILED: ["The project does not compile after the change."],
        VerificationKind.NONE: _RISKS_NONE,
    }.get(level, _RISKS_NONE)
    return VerificationReport(level=level, evidence=evidence or [], remaining_risks=list(risks))


@dataclass
class FixContext:
    """
    Everything an adapter needs to remediate, in a single object.

    Grouping the parameters here keeps propose_fix's signature from growing
    every time a capability is added (apply, generator, snapshot...). Adapters
    read from here; the core builds it.

    - project_root: the user's project root.
    - contract_new: path to the new contract (e.g. the downloaded swagger.json).
    - breaking_changes: human-readable diff report (currently oasdiff text).
    - llm: optional LLM provider to generate the fix (None = report only).
    - apply: if False, the adapter does NOT write to disk: it only proposes.
    """
    project_root: Path
    contract_new: Path
    breaking_changes: str = ""
    llm: object | None = None
    apply: bool = False


class LanguageAdapter(ABC):
    """Interface the core uses to talk to any language."""

    #: Short adapter name, e.g. "dotnet". Used in logs and selection.
    name: str = "base"

    @abstractmethod
    def detect(self, project_root: Path) -> bool:
        """
        Is this adapter the right one for the project at `project_root`?

        Must be cheap and non-destructive: look at file extensions, manifests
        (.csproj, package.json, etc.). Returns True if it recognizes the project
        as its own.
        """
        raise NotImplementedError

    def classify_client(self, project_root: Path) -> ClientClassification:
        """
        Classify how the project consumes the API, with evidence. Default
        implementation: UNKNOWN with no evidence. Adapters that can distinguish
        generated/manual/none override it (see DotNetAdapter). Part of the
        contract so the CLI needs no reflection.
        """
        return ClientClassification(kind=ClientKind.UNKNOWN)

    @abstractmethod
    def propose_fix(self, ctx: FixContext) -> RemediationResult:
        """
        Remediate the code affected by a breaking change, per `ctx`.

        Contract rules:
          - If ctx.apply is False, do NOT write to disk: only build the result
            (files_changed reflects what WOULD be done).
          - If ctx.llm is None, only report; don't invent fixes.
          - Do NOT commit or open a PR: that's the core's job.
        """
        raise NotImplementedError
