"""Shared verification-level string constants.

Kept in their own tiny module so both the adapters (which own VerificationKind)
and the core gates/exit-code logic can reference the same string values without
importing each other. These MUST match VerificationKind.*.value in
adapters/base.py.
"""

LEVEL_BUILD = "build"
LEVEL_INFERRED_BUILD = "inferred_build"
LEVEL_SYNTAX_ONLY = "syntax_only"
LEVEL_BUILD_FAILED = "build_failed"
LEVEL_NONE = "none"
