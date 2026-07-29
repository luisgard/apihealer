"""
APIHealer CLI.

Flow (with the cheap diff BEFORE the adapter):
    1. Ask for the project path.
    2. Detect language -> select adapter.
    3. Ask for the contract URL (today: Swagger).
    4. Fetch the contract (ContractSource) and diff against the snapshot.
    5. If there are breaking changes that affect us, the adapter proposes a fix.

Cross-platform: standard library only + external tools via PATH. Runs the same
on Windows, Linux and Mac.

Two axes of extensibility, both pluggable without touching the core:
  - Language adapters (adapters/): how to remediate the code.
  - Contract sources (core/contract_source.py): where the shape comes from.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapters import select_adapter
from .adapters.base import ClientKind, FixContext
from .core import diff as diff_mod
from .core.contract_source import SwaggerSource
from .core.llm_providers import available_providers, get_provider
from .core.snapshot_store import SnapshotStore



def _prompt(text: str, provided: str | None) -> str:
    if provided:
        return provided
    return input(text).strip()


def _info(msg: str) -> None:
    print(f"  {msg}")


def _step(msg: str) -> None:
    print(f"\n> {msg}")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apihealer",
        description="Detect API contract changes and remediate the consuming code.",
    )
    parser.add_argument("--path", help="Path to the project's main folder.")
    parser.add_argument("--swagger-url", help="URL of the swagger.json to watch.")
    parser.add_argument(
        "--name",
        help="Name for this API's baseline (e.g. 'stripe'). Lets one project "
             "watch several APIs without their snapshots colliding. If omitted, "
             "a hash of the URL is used.",
    )
    parser.add_argument(
        "--list-apis",
        action="store_true",
        help="List the APIs with a stored baseline in this project, then exit.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Allow the adapter to write changes to disk (default: propose only).",
    )
    parser.add_argument(
        "--llm",
        help="LLM provider for the automatic fix (or set APIHEALER_LLM).",
    )
    parser.add_argument(
        "--report",
        choices=["md", "json"],
        help="Emit a VerificationReport artifact in the given format (bridge to CI/CD).",
    )
    parser.add_argument(
        "--report-out",
        help="Write the report to this path instead of stdout.",
    )
    parser.add_argument(
        "--open-pr",
        action="store_true",
        help="After applying a fix, create a git branch and commit it, and "
             "print the PR title/body and the command to push and open the PR.",
    )
    parser.add_argument(
        "--pr-out",
        help="Write the generated PR body (Markdown) to this path (e.g. pr-body.md).",
    )
    parser.add_argument(
        "--apply-policy",
        choices=["verified", "safe", "permissive"],
        default="safe",
        help="Which verification levels are acceptable as an applied fix in CI. "
             "verified=only compiler-verified (build); safe=also inferred_build; "
             "permissive=also syntax_only (lower evidence). Decides the exit "
             "code; the fix is always reported. Default: safe.",
    )
    args = parser.parse_args(argv)

    print("=" * 60)
    print("  APIHealer  -  API contract auto-remediation")
    print("=" * 60)

    if not args.list_apis and not diff_mod.oasdiff_installed():
        print("\n[!] oasdiff is not installed or not on PATH.")
        print("    It's the tool that detects breaking changes.")
        print("    Install: https://github.com/oasdiff/oasdiff  (single binary, cross-platform)")
        return 2

    # Step 1: project path.
    _step("Step 1/5 - Project")
    raw_path = _prompt("  Path to the project's main folder: ", args.path)
    project_root = Path(raw_path).expanduser().resolve()
    if not project_root.is_dir():
        print(f"[!] The path doesn't exist or isn't a folder: {project_root}")
        return 1

    store = SnapshotStore(project_root)

    # --list-apis: show watched APIs in this project and exit.
    if args.list_apis:
        apis = store.list_apis()
        if not apis:
            _info("No API baselines stored in this project yet.")
        else:
            _info(f"APIs watched in this project ({len(apis)}):")
            for a in apis:
                _info(f"  - {a}")
        return 0
    _info(f"Project: {project_root}")

    # Step 2: detect language / adapter.
    _step("Step 2/5 - Language detection")
    adapter = select_adapter(project_root)
    if adapter is None:
        print("[!] No adapter recognized this project.")
        print("    Supported today: .NET. (Other languages: coming soon.)")
        return 1
    _info(f"Selected adapter: {adapter.name}")
    classification = adapter.classify_client(project_root)
    kind = classification.kind
    msg = {
        ClientKind.GENERATED: "API consumption: GENERATED client (reliable path, compiler safety net).",
        ClientKind.MANUAL: "API consumption: MANUAL (fix possible, but no compiler guarantee).",
        ClientKind.NONE: "No API consumption detected in this project.",
        ClientKind.UNKNOWN: "Client kind: unknown.",
    }.get(kind, "Client kind: unknown.")
    _info(msg)
    for reason in classification.reasons:
        _info(f"  - {reason}")

    # Step 3: contract source (today, Swagger).
    _step("Step 3/5 - API contract")
    swagger_url = _prompt("  URL of the swagger.json: ", args.swagger_url)
    if not swagger_url:
        print("[!] The contract URL is required.")
        return 1
    source = SwaggerSource(swagger_url)
    _info(f"Contract source: {source.name}")

    # Resolve this API's storage key (name if given, else hash of URL).
    api_key = store.resolve_key(args.name, swagger_url)
    _info(f"API baseline key: {api_key}")

    baseline_path = store.baseline_path(api_key)
    # Download the current contract to a temp path next to the baseline.
    new_snapshot = store.api_dir(api_key) / "contract_incoming.json"

    # Step 4: fetch and diff.
    _step("Step 4/5 - Change detection")
    try:
        source.fetch(new_snapshot)
    except Exception as exc:
        print(f"[!] Could not fetch the contract: {exc}")
        return 1
    _info("Contract fetched.")

    diff = diff_mod.diff_contracts(baseline_path, new_snapshot)

    if diff.first_run:
        _info(f"First run for '{api_key}': saved as baseline. Nothing to compare yet.")
        store.write_baseline(api_key, new_snapshot.read_bytes())
        new_snapshot.unlink(missing_ok=True)
        print("\nBaseline established. Commit .apihealer/ so CI shares it. "
              "Run again after the provider's next change.")
        return 0

    if not diff.changed:
        _info("The contract hasn't changed since last time. Nothing to do.")
        new_snapshot.unlink(missing_ok=True)
        return 0

    if not diff.has_breaking:
        _info("The contract changed, but with no breaking changes. Updating baseline.")
        store.write_baseline(api_key, new_snapshot.read_bytes())
        new_snapshot.unlink(missing_ok=True)
        return 0

    print("\n[!] Breaking changes detected:")
    print(_indent(diff.breaking_report))

    # Step 5: remediation via adapter.
    _step("Step 5/5 - Remediation")
    llm = get_provider(args.llm)
    if llm is None:
        _info(
            "No LLM configured: the exact points to fix will be reported. "
            f"For an automatic fix, set APIHEALER_LLM (options: {', '.join(available_providers())})."
        )
    else:
        _info(f"LLM: {llm.name}")
    if not args.apply:
        _info("Proposal mode (no --apply): no changes will be written to disk.")
    proposal = adapter.propose_fix(FixContext(
        project_root=project_root,
        contract_new=new_snapshot,
        breaking_changes=diff.breaking_report,
        llm=llm,
        apply=args.apply,
    ))

    print(_indent(proposal.summary))
    if proposal.notes:
        print("\n  Notes:")
        for n in proposal.notes:
            print(f"   - {n}")
    print(f"\n  Confidence: {proposal.confidence:.0%}  |  Verification: {proposal.verification.level.value}")
    if proposal.verification.evidence:
        print("  Evidence:")
        for e in proposal.verification.evidence:
            print(f"   + {e}")
    if proposal.verification.remaining_risks:
        print("  What can still be wrong:")
        for r in proposal.verification.remaining_risks:
            print(f"   ! {r}")

    if proposal.applied:
        _info("Changes applied to your working copy. Review the diff before committing.")
        store.write_baseline(api_key, new_snapshot.read_bytes())
        _info(f"Baseline for '{api_key}' updated. Commit .apihealer/ with your fix "
              "so the new contract travels in the same PR.")
    else:
        _info("No changes were applied automatically (proposal only).")
        _info("The baseline was NOT updated: the change is still pending.")
    new_snapshot.unlink(missing_ok=True)

    # Optional CI/CD artifact: the VerificationReport as Markdown or JSON.
    if args.report:
        from .core import report as report_mod
        rendered = report_mod.render(proposal, args.report)
        if args.report_out:
            out = Path(args.report_out).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rendered, encoding="utf-8")
            _info(f"Report written to {out}")
        else:
            print("\n" + rendered)

    # Optional Level-3 PR preparation: branch + commit + PR body. Host-agnostic;
    # APIHealer prepares everything and leaves the push to you (or a pipeline
    # with credentials).
    if args.open_pr or args.pr_out:
        from .core import pr as pr_mod
        if not proposal.applied:
            _info("Skipping PR: no fix was applied (run with --apply).")
        else:
            prep = pr_mod.prepare_pr(project_root, api_key, proposal)
            if args.pr_out:
                pout = Path(args.pr_out).expanduser()
                pout.parent.mkdir(parents=True, exist_ok=True)
                pout.write_text(prep.body, encoding="utf-8")
                _info(f"PR body written to {pout}")
            for n in prep.notes:
                _info(n)
            if args.open_pr:
                print("\n--- PR title ---")
                print(prep.title)
                print("\n--- Next: push and open the PR ---")
                print(pr_mod.pr_push_hint(prep.branch))

    # CI contract: policy gate + exit code, based on the verification LEVEL
    # (not the confidence number -- confidence explains, the level decides).
    from .core.gates import policy_allows
    from .core.exit_codes import exit_code_for, EXIT_UNREMEDIATED, EXIT_VERIFICATION_FAILED
    level = proposal.verification.level.value
    allowed = policy_allows(args.apply_policy, level)
    code = exit_code_for(
        applied=proposal.applied,
        level=level,
        breaking=True,  # we only reach here past the breaking-change gate
        allowed_by_policy=allowed,
    )
    if code == EXIT_UNREMEDIATED:
        _info(f"Policy '{args.apply_policy}' does not accept a '{level}' remediation as "
              "an applied fix; treating this run as a report. Exit code 2.")
    elif code == EXIT_VERIFICATION_FAILED:
        _info("The applied change does not compile (build_failed). Exit code 3.")
    return code


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
