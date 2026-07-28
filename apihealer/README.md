# APIHealer

Detects breaking API contract changes and applies remediations with explicit
verification levels, for API consumers. You run it, you review the result.

> **Python orchestrates; native tools do the work; the compiler verifies; the
> LLM only proposes.**

That line is the whole point. APIHealer is not "AI that magically fixes code."
It's a system that reports *with what level of evidence* it can claim a change
is repaired -- and never pretends a proposal is a proven fix.

APIHealer is not "AI first." It is:

```text
Contract intelligence  +  language tooling  +  compiler feedback  +  AI as assistant
```

## What it does

When an API you consume changes -- a third party's or another team's -- APIHealer
detects the change, proposes or applies a remediation, and leaves the result
ready for review, before contract drift causes failures in downstream consumers.

## Who uses APIHealer?

APIHealer is for teams that:

- consume internal APIs across multiple services;
- depend on third-party APIs (Stripe, Twilio, ...);
- maintain generated API clients (NSwag/Kiota/openapi-generator);
- want automated remediation without blind, unverifiable AI changes.

## Why regeneration is not enough

If you use NSwag, the obvious question is: *why not just regenerate the client?*

Because regenerating a typed client updates the *representation* of the API --
it does not update the application code that depends on the previous contract:

```text
API contract
      |
      v
Generated client   <- regeneration fixes this
      |
      v
Business code that consumes the client   <- but this is what breaks
```

Regeneration moves the break from "compiles fine, wrong at runtime" to "won't
compile" -- which is progress, but you still have to fix every consuming call
site. APIHealer focuses on that **consumer impact**: it regenerates, lets the
compiler locate the affected code, and remediates it.

## Verification model

APIHealer does not assign the same confidence to every fix. The client type
decides the strategy, the evidence that backs the result, and -- just as
important -- what can *still* be wrong afterward. This is not just README prose:
every result carries a `VerificationReport`:

```text
RemediationResult
   |
   +-- files changed
   +-- confidence
   +-- VerificationReport
          |
          +-- level (build / syntax_only / none)
          +-- evidence      (what was actually checked)
          +-- remaining_risks (what a pass does NOT prove)
```

| Client type | Strategy | Verification | Confidence | What can still be wrong |
|---|---|---|---|---|
| Generated (NSwag/Kiota/openapi-generator) | Regenerate + build | Compiler verified | High (type compatibility) | Runtime / business behavior (new enum meaning, nullability changing logic) |
| Manual (hand-written / Refit) | LLM-assisted remediation | Build/syntax only, where available | Medium / Low | Contract semantics -- may compile and still be wrong |
| None / Unknown | No automatic changes | Human review | n/a | Everything -- nothing was changed |

The distinction that matters: for a **generated** client, a passing recompile
proves the code fits the new contract's *generated types* -- references,
signatures, compilation. It does not prove serialization, validations, or
business logic. For a **manual** client, a passing compile only proves the
syntax is valid -- a business-rule change can compile and still be wrong.

## What APIHealer does not guarantee

APIHealer does **not** prove:

- API runtime behavior;
- business correctness;
- data-migration correctness;
- performance regressions;
- security implications.

It proves exactly the level of evidence reported in the `VerificationReport`,
and lists the residual risks for a human to check. Nothing more is claimed.

## Flow

```text
          OpenAPI Contract
                 |
                 v
          Current snapshot
                 |
                 v
              oasdiff  <----  Previous snapshot (baseline)
                 |
          breaking changes detected
                 |
                 v
            Language Adapter
                 |
            ClientClassifier
                 |
         +-------+-------+
         |               |
     Generated        Manual
         |               |
     regenerate      LLM inspect
         |               |
   compiler verify   build / tests
         |               |
         +-------+-------+
                 |
                 v
         RemediationResult
      (changes + confidence +
       VerificationReport)
                 |
                 v
              Review PR
```

APIHealer compares the current contract against a stored **baseline** snapshot
with oasdiff, and stops early if nothing changed or nothing is breaking. That
baseline comparison is why it's not just a linter: it reacts to *changes* over
time, not to the current spec in isolation.

## Example

Your provider restructures the response of `POST /messages` -- not a rename, a
reshape:

```jsonc
// before
{ "recipientId": 123, "body": "hello" }
// after
{ "recipient": { "id": 123 }, "content": "hello" }
```

For a generated .NET client, APIHealer:

1. Regenerates the client from the new contract.
2. Runs `dotnet build`.
3. Uses the compiler errors to find the affected usages (every place that read
   `recipientId` or `body` now fails to compile).
4. Applies a targeted fix (via the configured LLM).
5. Recompiles to verify -- and only then reports high confidence, with the
   residual risks still listed.

The generated path benefits from compiler feedback because generated DTOs encode
the contract into types: when the contract changes, the regenerated types stop
matching your code and the compiler points at every affected line. A manual
client encodes the contract loosely (e.g. a hand-written DTO with
`JsonPropertyName("recipientId")`), so the compiler stays silent -- there, the
LLM locates the impact from the contract diff instead, and confidence is lower
by design.

## CI/CD-ready reports

Any run can emit its `VerificationReport` as a shareable artifact -- the bridge
to CI/CD, before wiring any platform permissions:

```bash
apihealer --path . --swagger-url <url> --report md --report-out verification-report.md
apihealer --path . --swagger-url <url> --report json
```

```text
Pipeline
   |
   v
apihealer --report md
   |
   +--> verification-report.md  --->  PR comment / build artifact
```

## Watching multiple APIs

One project often consumes several APIs. Each gets its own baseline, keyed by a
name, so their snapshots never collide:

```bash
apihealer --path . --name orders   --swagger-url http://internal/orders/swagger.json
apihealer --path . --name payments --swagger-url https://api.stripe.com/openapi.json
apihealer --path . --list-apis     # see what this project watches
```

Baselines live in the repo at `.apihealer/<name>/contract.json` and are
committed like any other file. This is what makes it work the same locally and
in **ephemeral CI runners**: the runner clones the repo and the baseline is
already there. When a breaking change is remediated, the updated baseline
travels in the same PR as the fix -- so git is both the persistence and the
audit trail of how each contract evolved.

## Architecture

Two halves with a well-drawn boundary:

- **Core** (`apihealer/core`): language- and OS-agnostic. Asks for the path,
  detects the language, downloads the contract, diffs it with oasdiff and
  orchestrates. It works on the OpenAPI contract, not on your code, so it serves
  any language.
- **Adapters** (`apihealer/adapters`): the language-specific parts. Today only
  `.NET`. Each adapter fulfills the contract in `base.py` and invokes the
  language's native tools (nswag, dotnet) as external processes.

The .NET adapter is split by responsibility so the adapter itself is a thin
coordinator:

- `ClientClassifier` -- which client kind, and the evidence for it.
- `GeneratedFixStrategy` / `ManualFixStrategy` -- the two fix algorithms.
- `DotNetToolchain` -- all native tool calls (build, regenerate, parse errors).
- pluggable client generators -- NSwag / Kiota / openapi-generator.

### Two axes of extensibility

- **Language adapters** (`adapters/`): *how* to remediate the code. The mold
  (`Classifier` + `Strategy` + `Toolchain`) is ready to copy for a `JavaAdapter`,
  `PythonAdapter`, etc.
- **Contract sources** (`core/contract_source.py`): *where* the API shape comes
  from. Today: `SwaggerSource`.

Both axes grow without touching the core.

## Design principles

- **`applied` and `verification` are independent.** "I wrote it" is not "I know
  it's right." Every `RemediationResult` keeps them as separate fields.
- **Confidence reflects evidence.** Generated + build-verified earns high
  confidence; manual earns medium/low by design.
- **Fail closed.** When APIHealer cannot establish enough evidence, it reports
  the uncertainty instead of applying a confident-looking guess.
- **Changes are staged transactionally:** if a multi-file remediation fails, the
  working tree is restored -- your repo never ends up half-changed.
- **The LLM is pluggable and can be local.** Claude, Ollama (Gemma, Qwen...),
  or others, chosen by env var. Local keeps your code on your machine.

## Current implementation

Implemented:

- .NET adapter (thin coordinator over classifier + strategies + toolchain);
- NSwag / Kiota / openapi-generator detection;
- OpenAPI breaking-change detection via oasdiff, against a baseline snapshot;
- compiler-backed remediation loop (regenerate -> build -> fix -> recompile);
- manual-client remediation with build/syntax verification where available;
- transactional file changes with rollback;
- pluggable LLM providers (Claude, local Ollama);
- structured `VerificationReport` and Markdown/JSON report output.

## Requirements

- Python 3.10+
- [oasdiff](https://github.com/oasdiff/oasdiff) on PATH (single binary,
  cross-platform).
- For the .NET adapter: the `dotnet` SDK and, if you use NSwag, `nswag` on PATH.
- Optional LLM: `ANTHROPIC_API_KEY` for Claude, or a running Ollama for local.

## Usage

```bash
# install (from the project folder)
pip install -e .

# run interactively (proposal mode: nothing is written)
apihealer

# pass inputs and let it write the fix
apihealer --path /path/to/my/project \
          --swagger-url https://other-team/swagger/v1/swagger.json \
          --apply

# emit a CI/CD report
apihealer --path . --swagger-url <url> --report md --report-out verification-report.md

# choose the LLM
APIHEALER_LLM=ollama APIHEALER_LLM_MODEL=gemma4 apihealer --apply
APIHEALER_LLM=claude ANTHROPIC_API_KEY=... apihealer --apply
```

The first run establishes the baseline. Run again after a provider change to
detect and remediate.

## Future work

- Git / Azure DevOps integration to open the PR from the applied fix (the report
  artifact is the bridge already in place).
- **Planned contract sources:** `InferredSource`, which derives a partial
  contract from observed endpoint responses, for old APIs that don't publish a
  spec (the abstraction is already in place). Later: GraphQL, gRPC.
- Other languages (the adapter mold is ready to copy).
- Structured diff output and richer related-context extraction for the LLM.
- Auth for protected Swaggers and webhook triggering.
