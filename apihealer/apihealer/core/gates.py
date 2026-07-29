"""
Verification gates -- deciding whether a remediation may be applied.

The decision unit is the *verification level*, not the confidence number. This
is deliberate and matches the whole thesis: confidence explains, it doesn't
judge. "How much can you prove?" (the level) is the right question for a gate;
"how sure does the model feel?" (a raw threshold) is not. Confidence remains as
evidence in the report, never as the arbiter.

A policy names which levels are allowed to be written to disk. Anything below
the policy is downgraded to a report -- detected and explained, but not applied.

Policies (least to most permissive):
  verified   -> only `build` (compiler-verified, generated path)
  safe       -> `build` and `inferred_build` (inference that at least compiles)
  all        -> any remediation, including `syntax_only`

`build_failed` is never "allowed" by any policy: a change that doesn't compile
is never an acceptable applied outcome. It surfaces as a failure, not a fix.
"""

from __future__ import annotations

from .base_levels import LEVEL_BUILD, LEVEL_INFERRED_BUILD, LEVEL_SYNTAX_ONLY

POLICIES: dict[str, set[str]] = {
    "verified": {LEVEL_BUILD},
    "safe": {LEVEL_BUILD, LEVEL_INFERRED_BUILD},
    "permissive": {LEVEL_BUILD, LEVEL_INFERRED_BUILD, LEVEL_SYNTAX_ONLY},
}

DEFAULT_POLICY = "safe"


def policy_allows(policy: str, level: str) -> bool:
    """Does this policy permit applying a remediation at this verification level?"""
    return level in POLICIES.get(policy, POLICIES[DEFAULT_POLICY])


def policy_names() -> list[str]:
    return list(POLICIES.keys())
