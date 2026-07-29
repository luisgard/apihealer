"""
Exit codes -- APIHealer's contract with a CI pipeline.

A pipeline needs to branch on the outcome, so the exit code is a stable,
documented interface. The codes describe *what happened to the verification*,
consistent with the rest of the tool: the level, and whether the applied result
was acceptable under the active policy.

  0  OK. No breaking change, or a remediation was applied within policy.
  1  Execution error (bad config, Swagger unreachable, missing toolchain).
  2  Breaking change detected but NOT remediated within policy
     (left as a report: e.g. inferred fix under a `verified` policy).
  3  A remediation was applied but verification FAILED (build_failed).

A pipeline chooses its own strictness by which non-zero codes it fails on. By
default many teams fail on 1 and 3, and treat 2 as "open an informational PR."
"""

from __future__ import annotations

from .base_levels import LEVEL_BUILD_FAILED

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNREMEDIATED = 2
EXIT_VERIFICATION_FAILED = 3


def exit_code_for(*, applied: bool, level: str, breaking: bool,
                  allowed_by_policy: bool) -> int:
    """Map an outcome to an exit code. Pure function, easy to test."""
    if not breaking:
        return EXIT_OK
    if level == LEVEL_BUILD_FAILED:
        return EXIT_VERIFICATION_FAILED
    if applied and allowed_by_policy:
        return EXIT_OK
    # breaking change that wasn't applied within policy -> left as a report
    return EXIT_UNREMEDIATED
