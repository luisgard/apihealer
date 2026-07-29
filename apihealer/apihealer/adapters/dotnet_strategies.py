"""
Remediation strategies for .NET.

Strategy pattern: two interchangeable algorithms with the same input
(FixContext) and output (FixProposal). The project's philosophical distinction
--"what the compilation guarantees"-- is embodied in the STRUCTURE:
  - GeneratedFixStrategy verifies with the compiler -> can assert high confidence.
  - ManualFixStrategy structurally CANNOT assert that -> medium/low confidence.

Both receive a DotNetToolchain and a ClientClassifier by injection; they don't
invoke tools or re-read the project on their own.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..core.confidence import (
    score_generated_clean,
    score_generated_verified,
    score_manual_inferred_build,
    score_manual_suggested,
    score_build_failed,
)
from ..core.file_tx import FileTransaction
from ..core.llm import build_fix_prompt
from .base import (
    FixContext,
    RemediationResult,
    VerificationKind,
    verification_report,
)
from .dotnet_classifier import ClientClassifier
from .dotnet_toolchain import DotNetToolchain


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


class FixStrategy(ABC):
    """Contract of a remediation strategy."""

    def __init__(self, toolchain: DotNetToolchain, classifier: ClientClassifier):
        self.tc = toolchain
        self.classifier = classifier

    @abstractmethod
    def fix(self, ctx: FixContext) -> FixProposal:
        raise NotImplementedError


class GeneratedFixStrategy(FixStrategy):
    """
    Regenerable client: regenerate -> build -> compiler errors -> LLM ->
    RECOMPILE to verify. The compiler is the safety net; that's why this
    strategy can return high confidence and verification=BUILD.
    """

    def fix(self, ctx: FixContext) -> FixProposal:
        manifest_text = self.classifier._read_manifest_text(ctx.project_root)
        generator = self.tc.select_generator(ctx.project_root, manifest_text)
        if generator is None:
            return RemediationResult(
                summary="Could not identify the client generator.",
                verification=verification_report(VerificationKind.NONE),
                notes=["Classified as GENERATED but no generator recognized."],
            )

        if not ctx.apply:
            return RemediationResult(
                summary=(
                    f"[proposal] Would regenerate the client with {generator.name}, "
                    "compile, and adapt the affected code.\n\n"
                    "Contract changes:\n" + ctx.breaking_changes
                ),
                verification=verification_report(VerificationKind.NONE),
                notes=["Proposal mode (apply=False): nothing was written."],
            )

        if not generator.available():
            return RemediationResult(
                summary=(
                    f"The project uses {generator.name}, but '{generator.tool}' is "
                    "not installed; could not regenerate the client."
                ),
                verification=verification_report(VerificationKind.NONE),
                notes=[f"Install {generator.tool} to enable the generated path."],
            )

        regen = self.tc.regenerate(generator, ctx.project_root, ctx.contract_new)
        if not regen.ok:
            return RemediationResult(
                summary=f"Failed to regenerate the client with {generator.name}.",
                verification=verification_report(VerificationKind.NONE),
                notes=[regen.stderr.strip() or "unknown generator failure"],
            )

        build = self.tc.build(ctx.project_root)
        if build is None:
            return RemediationResult(
                summary="dotnet is not available; could not compile.",
                verification=verification_report(VerificationKind.NONE),
                notes=["Install the .NET SDK to enable the generated path."],
            )

        if build.ok:
            sc = score_generated_clean()
            return RemediationResult(
                files_changed=["(client regenerated)"],
                summary=(
                    "The client was regenerated and the project compiles with no "
                    "additional changes.\n\nContract changes:\n" + ctx.breaking_changes
                ),
                confidence=sc.total,
                confidence_factors=sc.breakdown(),
                applied=True,
                verification=verification_report(
                    VerificationKind.BUILD,
                    ["Client regenerated from the new contract.", "dotnet build passed with no further changes."],
                ),
            )

        errors = self.tc.parse_compiler_errors(build.stdout + "\n" + build.stderr)
        errors_text = "\n".join(f"- {e['file']}:{e['line']} {e['message']}" for e in errors)

        if ctx.llm is None:
            return RemediationResult(
                files_changed=[e["file"] for e in errors if e.get("file")],
                summary=(
                    "The client was regenerated and errors appeared where your code "
                    "uses what changed:\n\n" + errors_text
                    + "\n\nContract changes:\n" + ctx.breaking_changes
                ),
                confidence=0.5,
                verification=verification_report(VerificationKind.BUILD_FAILED),
                notes=["Configure an LLM (APIHEALER_LLM) for the automatic fix."],
            )

        fixed = self._llm_fix_files(
            ctx.project_root,
            sorted({e["file"] for e in errors if e.get("file")}),
            ctx.breaking_changes,
            errors_text,
            ctx.llm,
            require_change=False,
        )
        if not fixed["files"]:
            return RemediationResult(
                summary="The LLM could not generate an applicable fix:\n\n" + errors_text,
                confidence=0.2,
                verification=verification_report(VerificationKind.BUILD_FAILED),
                notes=fixed["notes"],
            )

        verify = self.tc.build(ctx.project_root)
        if verify is not None and verify.ok:
            sc = score_generated_verified()
            return RemediationResult(
                files_changed=fixed["files"],
                summary=(
                    "The client was regenerated, the LLM adapted the code and the "
                    "project COMPILES after the fix. Review the diff before "
                    "committing.\n\nContract changes:\n" + ctx.breaking_changes
                ),
                confidence=sc.total,
                confidence_factors=sc.breakdown(),
                applied=True,
                verification=verification_report(
                    VerificationKind.BUILD,
                    ["Client regenerated.", "LLM adapted the affected code.", "dotnet build passed after the fix."],
                ),
                notes=fixed["notes"],
            )

        remaining = ""
        if verify is not None:
            remaining = "\n".join(
                f"- {e['file']}:{e['line']} {e['message']}"
                for e in self.tc.parse_compiler_errors(verify.stdout + "\n" + verify.stderr)
            )
        return RemediationResult(
            files_changed=fixed["files"],
            summary=(
                "The LLM applied changes but the project STILL doesn't compile.\n\n"
                "Remaining errors:\n" + remaining
            ),
            confidence=0.3,
            applied=True,
            verification=verification_report(VerificationKind.BUILD_FAILED),
            notes=fixed["notes"] + ["Needs human review: doesn't compile yet."],
        )

    def _llm_fix_files(self, project_root, files, breaking_changes, errors_text, llm, require_change) -> dict:
        changed: list[str] = []
        notes: list[str] = []
        tx = FileTransaction()
        try:
            for file_path in files:
                p = Path(file_path)
                if not p.is_absolute():
                    p = project_root / file_path
                if not p.exists():
                    notes.append(f"Reported file not found: {file_path}")
                    continue
                try:
                    original = p.read_text(encoding="utf-8", errors="ignore")
                except Exception as exc:
                    notes.append(f"Could not read {file_path}: {exc}")
                    continue
                system, user = build_fix_prompt("C#", breaking_changes, errors_text, original)
                resp = llm.complete(system, user)
                if not resp.ok or not resp.text.strip():
                    notes.append(f"The LLM returned no fix for {file_path}: {resp.error or 'empty'}")
                    continue
                new_code = _strip_code_fences(resp.text)
                if require_change and new_code.strip() == original.strip():
                    continue
                tx.write(p, new_code)
                changed.append(str(p.relative_to(project_root)))
            tx.commit()
        except Exception as exc:
            tx.rollback()
            notes.append(f"Write failed; all changes rolled back: {exc}")
            return {"files": [], "notes": notes}
        return {"files": changed, "notes": notes}


class ManualFixStrategy(FixStrategy):
    """
    Hand-written client / Refit: there's no regeneration, so the compiler CANNOT
    confirm that the adaptation to the contract is complete. The LLM locates the
    impact from the contract diff. Medium/low confidence by design, even if it
    compiles.
    """

    HONEST_TAIL = (
        "\n\nNOTE: this is a MANUAL client. Even if the project compiles, "
        "compilation does not guarantee the adaptation to the contract is "
        "complete (a business-rule change can compile and still be wrong). "
        "Review the diff and run your tests."
    )

    def fix(self, ctx: FixContext) -> FixProposal:
        if ctx.llm is None:
            return RemediationResult(
                summary=(
                    "Manual client detected. Without an LLM no fix is proposed; "
                    "review the contract change by hand:\n\n"
                    + ctx.breaking_changes + self.HONEST_TAIL
                ),
                verification=verification_report(VerificationKind.NONE),
                notes=["Manual client. Configure APIHEALER_LLM."],
            )

        candidates = self.classifier.api_consuming_files(ctx.project_root)
        if not candidates:
            return RemediationResult(
                summary=(
                    "Manual client, but no clear consuming files were located. "
                    "Review by hand:\n\n" + ctx.breaking_changes + self.HONEST_TAIL
                ),
                confidence=0.1,
                verification=verification_report(VerificationKind.NONE),
                notes=["No candidate API-consuming files found."],
            )

        if not ctx.apply:
            return RemediationResult(
                files_changed=[str(p.relative_to(ctx.project_root)) for p in candidates],
                summary=(
                    "[proposal] Manual client: the LLM would be asked to adapt the "
                    f"{len(candidates)} consuming file(s) from the contract diff."
                    + self.HONEST_TAIL
                    + "\n\nContract changes:\n" + ctx.breaking_changes
                ),
                verification=verification_report(VerificationKind.NONE),
                notes=["Proposal mode (apply=False): nothing was written."],
            )

        fixed = self._llm_fix_manual(ctx.project_root, candidates, ctx.breaking_changes, ctx.llm)
        if not fixed["files"]:
            return RemediationResult(
                summary=(
                    "The LLM proposed no changes to the manual client. Review the "
                    "contract by hand:\n\n" + ctx.breaking_changes + self.HONEST_TAIL
                ),
                confidence=0.1,
                verification=verification_report(VerificationKind.NONE),
                notes=fixed["notes"],
            )

        build = self.tc.build(ctx.project_root)
        if build is None:
            note = "Applied an inferred remediation, but dotnet is missing so it wasn't compiled."
            sc, ver, evidence = score_manual_suggested(), VerificationKind.NONE, []
        elif build.ok:
            note = "Applied an inferred remediation and verified it compiles."
            sc, ver = score_manual_inferred_build(), VerificationKind.INFERRED_BUILD
            evidence = [
                "Inferred the new shape from the contract diff and applied it.",
                "dotnet build passed: types and references are consistent.",
            ]
        else:
            note = "Applied an inferred remediation, but the project does NOT compile: review carefully."
            sc, ver, evidence = score_build_failed(), VerificationKind.BUILD_FAILED, []

        return RemediationResult(
            files_changed=fixed["files"],
            summary=(
                note + self.HONEST_TAIL
                + "\n\nContract changes:\n" + ctx.breaking_changes
            ),
            confidence=sc.total,
            confidence_factors=sc.breakdown(),
            applied=True,
            verification=verification_report(ver, evidence),
            notes=fixed["notes"] + ["Manual client: the field mapping was inferred, not compiler-proven."],
        )

    def _llm_fix_manual(self, project_root, candidates, breaking_changes, llm) -> dict:
        changed: list[str] = []
        notes: list[str] = []
        no_errors = "(no compiler errors; locate impact from the diff)"
        tx = FileTransaction()
        try:
            for p in candidates:
                try:
                    original = p.read_text(encoding="utf-8", errors="ignore")
                except Exception as exc:
                    notes.append(f"Could not read {p}: {exc}")
                    continue
                system, user = build_fix_prompt("C#", breaking_changes, no_errors, original, infer=True)
                resp = llm.complete(system, user)
                if not resp.ok or not resp.text.strip():
                    notes.append(f"The LLM returned no fix for {p.name}: {resp.error or 'empty'}")
                    continue
                new_code = _strip_code_fences(resp.text)
                if new_code.strip() == original.strip():
                    continue
                tx.write(p, new_code)
                changed.append(str(p.relative_to(project_root)))
            tx.commit()
        except Exception as exc:
            tx.rollback()
            notes.append(f"Write failed; all changes rolled back: {exc}")
            return {"files": [], "notes": notes}
        return {"files": changed, "notes": notes}
