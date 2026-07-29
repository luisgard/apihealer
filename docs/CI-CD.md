# CI/CD adoption

APIHealer is designed to drop into a pipeline with minimal friction. The guiding
principle: **APIHealer is an executable. If you can run a command in your
pipeline, you can use it.**

The **analysis engine is host-agnostic**: APIHealer receives your code and an
**API contract** — currently supplied as an OpenAPI/Swagger document — produces
a report, and returns an exit code. The same tool works in Azure DevOps (YAML or
classic), GitHub Actions, and GitLab CI. Pull request creation is the only
host-specific step, and it uses the native CLI of your repository provider —
nothing proprietary to APIHealer.

You adopt it in three levels, and each level is useful on its own.

## Level 1 — Run it in any pipeline (CLI only)

APIHealer runs as a command that points at the project and the contract and
emits a report. It knows nothing about your CI host.

```yaml
- script: |
    pip install apihealer
    apihealer \
      --path $(Build.SourcesDirectory) \
      --name orders \
      --swagger-url https://api.company.com/swagger/v1/swagger.json \
      --report md \
      --report-out apihealer-report.md
  displayName: APIHealer contract check
```

> Distribution: the intended install is `pip install apihealer` from PyPI
> **when published**. During development, install from a checkout with
> `pip install -e ./apihealer`. A container image (`apihealer/cli:latest`) is a
> planned distribution path for pinned CI use.

The same block works in **GitHub Actions** (`run:`) and **GitLab CI**
(`script:`). On Windows agents, use `python -m apihealer.cli` if the command
isn't on PATH.

## Security model

APIHealer starts from a minimum-permissions posture:

- **No long-lived tokens.** APIHealer stores no credentials of its own.
- **No repository installation.** Nothing is installed into your repo or org; it
  runs as a command in the agent you already trust.
- **Credentials come from the pipeline runtime.** The push/PR step uses the
  agent's existing git and provider credentials — APIHealer never handles them.
- **Workspace-scoped.** APIHealer reads the project workspace and the contract
  URL you give it, and writes only within the workspace. LLM use, if enabled,
  sends only the affected code to the provider you configured (or a local model,
  which keeps code on your machine). APIHealer never requires sending the full
  repository to an LLM provider.


## Level 2 — Publish the report as an artifact

```yaml
- task: PublishBuildArtifacts@1
  inputs:
    pathToPublish: apihealer-report.md
    artifactName: apihealer
```

Every run leaves a `verification-report.md` the team can open: what the API
changed, what APIHealer attempted, the verification level, the confidence, and
the residual risks — no PR required yet.

```text
Build → APIHealer → verification-report.md → Artifact
```

## Level 3 — Open a PR from the fix

At this stage APIHealer becomes an automated remediation step in the delivery
workflow. It prepares everything a PR needs — a branch, a descriptive commit,
and a PR body built from the VerificationReport — using plain git. Pushing and
opening the PR uses your provider's native CLI and your pipeline's existing
credentials.

```bash
apihealer \
  --path . --name orders \
  --swagger-url https://api.company.com/swagger/v1/swagger.json \
  --apply --apply-policy safe \
  --open-pr --pr-out pr-body.md
```

```bash
# Azure DevOps
git push -u origin apihealer/remediate-orders-<level>
az repos pr create --source-branch apihealer/remediate-orders-<level> \
  --title "APIHealer: remediation for 'orders' contract change" \
  --description @pr-body.md

# GitHub
gh pr create --head apihealer/remediate-orders-<level> \
  --title "APIHealer: remediation for 'orders' contract change" \
  --body-file pr-body.md
```

The reviewer opens a PR with the remediation, the verification level, the
evidence behind it, and the residual risks that remain even after a passing
check. That is the difference between "a bot changed code" and a remediation
that states exactly how much of itself is proven.

The full loop:

```text
API change → detection → analysis → remediation → PR → review → merge
```

## Guardrails: what APIHealer will and won't apply

APIHealer separates *proposing* a remediation from *proving* it. Apply
policies operate on what could be **verified**, not simply on what could be
generated. What it may apply is governed by `--apply-policy`, and the gate is
the **verification level** — how much can be proven — not the confidence number.
(Confidence explains the result; the level decides the gate.)

| Policy | Applies levels | Meaning |
|---|---|---|
| `verified` | `build` | Only compiler-verified fixes (generated clients). |
| `safe` (default) | `build`, `inferred_build` | Also inferred fixes that at least compile. |
| `permissive` | `build`, `inferred_build`, `syntax_only` | Also lower-evidence suggestions (use with care). |

A remediation whose level is below the active policy is **left as a report**,
not applied — detected and explained, but not written. A change that doesn't
compile (`build_failed`) is never an acceptable applied outcome under any policy.

Concretely, APIHealer's scope is: it edits the consumer code affected by the
contract change (regenerating a generated client, or creating/renaming DTOs and
updating usages for a manual one), and for generated clients it recompiles to
verify. It does not run your test suite, and it does not touch code unrelated to
the contract change.

## Exit codes

The exit code is APIHealer's contract with the pipeline, so a pipeline can
branch on it.

The **report is the source of truth** about what happened; the exit code is
just the pipeline decision derived from it.

| Code | Meaning |
|---|---|
| `0` | Pipeline-safe completion (nothing to fix, or a remediation applied within policy). |
| `1` | Execution failure (bad config, Swagger unreachable, missing toolchain). |
| `2` | Verification gate not satisfied (a breaking change was left as a report). |
| `3` | Applied remediation failed verification (`build_failed`). |

A team picks its own strictness by which non-zero codes fail the build. A common
choice: fail on `1` and `3`, and treat `2` as "open an informational PR." For
example, to block only hard failures:

```yaml
- script: apihealer --path . --name orders --swagger-url <url> --apply --apply-policy verified
  # exit 2 (unremediated under 'verified') won't fail the step unless you make it;
  # exit 1 and 3 will, as real errors.
```

## Classic pipelines work the same

A classic (non-YAML) pipeline is just another way to run commands: a **Command
Line** task running `apihealer ...`, then a **Publish Artifact** task. Same
engine, same flags — there is no separate product for classic vs YAML.

```text
                  APIHealer CLI
                       |
        +--------------+--------------+
        |                             |
   Developer local              CI/CD agent
                                      |
                    +-----------------+----------------+
                    |                                  |
              Azure YAML                     Azure classic
              (script task)                (command-line task)
                    |                                  |
                    +---------- report / PR -----------+
```

## Why not a marketplace extension (yet)

APIHealer adapts to the platform you already have rather than asking the platform
to adopt it. The CLI + report + documented pipeline task + PR flow make it
usable by a team today, with the minimum permissions model above. A Marketplace
extension (with its publishing, approval, and security-review overhead) is a
later convenience, not a prerequisite — and for teams with tool fatigue, "fits
the platform you already run" is the point.
