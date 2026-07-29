"""
Explainable confidence scoring.

Confidence is not a magic number. It's the sum of named factors, each tied to a
signal the system actually has -- did it compile? is the client generated or
manual? was the mapping inferred? -- so a user can see *why* it's 0.65 and not
0.70. This keeps the confidence itself as auditable as the rest of the tool: a
verification-aware tool shouldn't hide how it reaches its own number.

Each factor carries a short reason and a delta. The total is clamped to [0, 1].
We start with the factors we genuinely know today; finer signals (e.g. field-name
similarity between the removed and added properties) can be added later as real
inputs, not invented weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfidenceFactor:
    reason: str      # human-readable, e.g. "compiled successfully"
    delta: float     # signed contribution, e.g. +0.10


@dataclass
class ConfidenceScore:
    factors: list[ConfidenceFactor] = field(default_factory=list)

    def add(self, reason: str, delta: float) -> "ConfidenceScore":
        self.factors.append(ConfidenceFactor(reason, delta))
        return self

    @property
    def total(self) -> float:
        raw = sum(f.delta for f in self.factors)
        return max(0.0, min(1.0, round(raw, 3)))

    def breakdown(self) -> list[str]:
        """One line per factor, signed, for display: '+0.40 base: generated client'."""
        return [f"{('+' if f.delta >= 0 else '')}{f.delta:.2f}  {f.reason}" for f in self.factors]


# --- Builders per path: only signals the system truly has today ---------------

def score_generated_verified() -> ConfidenceScore:
    """Generated client, regenerated, LLM-fixed, and recompiled OK."""
    return (ConfidenceScore()
            .add("base: generated client (compiler can pinpoint impact)", 0.40)
            .add("client regenerated from the new contract", 0.15)
            .add("recompiled successfully after the fix (compiler-verified)", 0.40)
            .add("residual: runtime/business behavior not exercised", -0.10))


def score_generated_clean() -> ConfidenceScore:
    """Generated client that compiled with no code changes needed."""
    return (ConfidenceScore()
            .add("base: generated client", 0.40)
            .add("client regenerated from the new contract", 0.15)
            .add("compiles with no business-code changes needed", 0.40)
            .add("residual: runtime/business behavior not exercised", -0.05))


def score_manual_inferred_build() -> ConfidenceScore:
    """Manual client, inference applied, and it compiles."""
    return (ConfidenceScore()
            .add("base: manual client (no compiler signal to find impact)", 0.40)
            .add("remediation inferred from the contract diff and applied", 0.15)
            .add("recompiled successfully: types and references consistent", 0.30)
            .add("semantic mapping was inferred, not proven", -0.20))


def score_manual_suggested() -> ConfidenceScore:
    """Manual client, a change was written but not (or not yet) compile-verified."""
    return (ConfidenceScore()
            .add("base: manual client", 0.30)
            .add("a remediation was suggested from the contract diff", 0.10)
            .add("not verified by compilation", -0.20))


def score_build_failed() -> ConfidenceScore:
    return (ConfidenceScore()
            .add("a change was applied", 0.20)
            .add("project does not compile after the change", -0.30))
