"""
Detecting breaking changes between two contract artifacts.

PURE CORE, agnostic to both language AND source: it receives two files (the
previous snapshot and the current one, produced by any ContractSource) and
compares them. The diff is done by oasdiff, which already encodes the OpenAPI
compatibility rules correctly; we don't reimplement them.

Fetching the contract no longer lives here: that's done by the ContractSource
(see core/contract_source.py). This keeps the diff engine independent of
whether the contract came from a published Swagger or an inferred shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tools import run_tool, tool_available


@dataclass
class DiffResult:
    first_run: bool          # no previous snapshot: nothing to compare yet
    changed: bool            # the contract changed vs the snapshot
    has_breaking: bool       # there are incompatible changes
    breaking_report: str     # human-readable oasdiff output (for the PR)


def diff_contracts(old_path: Path, new_path: Path) -> DiffResult:
    """
    Compare two contract artifacts. If there's no previous snapshot
    (`old_path` doesn't exist), it's the first run: nothing to compare yet.
    """
    if not old_path.exists():
        return DiffResult(first_run=True, changed=False, has_breaking=False, breaking_report="")

    # Did anything change at all? Cheap byte comparison before oasdiff.
    if old_path.read_bytes() == new_path.read_bytes():
        return DiffResult(first_run=False, changed=False, has_breaking=False, breaking_report="")

    # oasdiff does the hard work: classifying breaking vs non-breaking.
    result = run_tool(["oasdiff", "breaking", str(old_path), str(new_path)])

    # oasdiff exits with a non-zero code when it FINDS breaking changes.
    # We tell "found breaking" from "real failure" by looking at stderr.
    has_breaking = bool(result.stdout.strip()) and "error" not in result.stderr.lower()
    report = result.stdout.strip() or result.stderr.strip()

    return DiffResult(first_run=False, changed=True, has_breaking=has_breaking, breaking_report=report)


def oasdiff_installed() -> bool:
    return tool_available("oasdiff")
