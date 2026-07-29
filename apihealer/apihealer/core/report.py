"""
Report rendering: turn a RemediationResult into a shareable artifact.

This is the bridge to CI/CD. Before wiring Azure DevOps / GitHub permissions,
`apihealer report` can emit a human-readable Markdown file or machine-readable
JSON, which a pipeline can later post as a PR comment or attach as an artifact.

The report centers the VerificationReport -- evidence, confidence and residual
risks -- because that's the differentiator: not "the AI changed code" but "here
is exactly how much we can claim, and what a human must still check".
"""

from __future__ import annotations

import json

from ..adapters.base import RemediationResult


def to_dict(result: RemediationResult) -> dict:
    """Machine-readable view of a remediation result."""
    v = result.verification
    return {
        "applied": result.applied,
        "confidence": round(result.confidence, 3),
        "confidence_factors": list(result.confidence_factors),
        "files_changed": list(result.files_changed),
        "verification": {
            "level": v.level.value,
            "evidence": list(v.evidence),
            "remaining_risks": list(v.remaining_risks),
        },
        "notes": list(result.notes),
        "summary": result.summary,
    }


def to_json(result: RemediationResult, indent: int = 2) -> str:
    return json.dumps(to_dict(result), indent=indent, ensure_ascii=False)


def to_markdown(result: RemediationResult) -> str:
    """Human-readable report, suitable as a PR comment body."""
    v = result.verification
    conf_pct = f"{result.confidence:.0%}"
    lines: list[str] = []
    lines.append("# APIHealer remediation report")
    lines.append("")
    lines.append(f"- **Applied:** {'yes' if result.applied else 'no (proposal only)'}")
    lines.append(f"- **Confidence:** {conf_pct}")
    lines.append(f"- **Verification level:** `{v.level.value}`")
    lines.append("")

    if result.files_changed:
        lines.append("## Files changed")
        for f in result.files_changed:
            lines.append(f"- `{f}`")
        lines.append("")

    if v.evidence:
        lines.append("## Evidence")
        for e in v.evidence:
            lines.append(f"- {e}")
        lines.append("")

    if result.confidence_factors:
        lines.append("## Why this confidence")
        for f in result.confidence_factors:
            lines.append(f"- `{f}`")
        lines.append("")

    if v.remaining_risks:
        lines.append("## What can still be wrong")
        for r in v.remaining_risks:
            lines.append(f"- {r}")
        lines.append("")

    if result.notes:
        lines.append("## Notes")
        for n in result.notes:
            lines.append(f"- {n}")
        lines.append("")

    if result.summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(result.summary)
        lines.append("")

    return "\n".join(lines)


def render(result: RemediationResult, fmt: str) -> str:
    """Render `result` in the requested format ('md' or 'json')."""
    if fmt == "json":
        return to_json(result)
    return to_markdown(result)
