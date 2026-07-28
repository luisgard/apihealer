# APIHealer

**Automated API contract remediation for API consumers.** When an API you
consume changes -- a third party's or another team's -- APIHealer detects the
breaking change, remediates the code that depends on it, and reports *with what
level of evidence* the fix can be trusted.

> **Python orchestrates; native tools do the work; the compiler verifies; the
> LLM only proposes.**

This is not "AI that magically fixes code." It's a contract-driven remediation
engine that uses deterministic tooling where it exists (OpenAPI diffing, client
regeneration, the compiler) and treats the LLM as an assistant whose output is
verified, not trusted blindly.

---

## Repository layout

This repo contains two things:

| Folder | What it is |
|---|---|
| [`apihealer/`](./apihealer) | **The tool.** A Python CLI that detects contract changes and remediates consuming code. Start here. |
| [`testbench/`](./testbench) | **A runnable demo.** Small .NET projects (a provider API + a generated client + a manual client) that let you see the tool work end to end, both paths. |

```text
.
├── apihealer/          # the tool (Python)
│   ├── apihealer/      # package: core + language adapters
│   ├── README.md       # full documentation, architecture, verification model
│   └── pyproject.toml
└── testbench/          # local .NET projects to try it against
    ├── OrdersApi/      # provider API (v1/v2 contracts)
    ├── Client.NSwag/   # generated client (reliable path)
    ├── Client.Manual/  # hand-written client (honest, lower-confidence path)
    └── contracts/      # captured swagger-v1.json / swagger-v2.json
```

---

## The core idea in one table

Not every fix earns the same confidence. The client type decides the strategy,
the evidence behind the result, and what can still be wrong afterward:

| Client type | Strategy | Verification | Confidence | What can still be wrong |
|---|---|---|---|---|
| Generated (NSwag/Kiota/openapi-generator) | Regenerate + build | Compiler verified | High (type compatibility) | Runtime / business behavior |
| Manual (hand-written / Refit) | LLM-assisted remediation | Build/syntax only | Medium / Low | Contract semantics -- may compile and still be wrong |
| None / Unknown | No automatic changes | Human review | n/a | Everything -- nothing was changed |

Every run produces a structured `VerificationReport` (evidence + confidence +
residual risks), which can be emitted as Markdown or JSON for CI/CD.

---

## Quick start

```bash
# 1. install the tool
cd apihealer
pip install -e .

# 2. see it work against the included demo (see testbench/README.md for the full walkthrough)
cd ../testbench
# run the provider API, point APIHealer at its swagger, switch the contract, re-run
```

- Full tool documentation, architecture and design principles:
  **[apihealer/README.md](./apihealer/README.md)**
- Step-by-step demo of both the generated and manual paths:
  **[testbench/README.md](./testbench/README.md)**

---

## Requirements

- Python 3.10+
- [oasdiff](https://github.com/oasdiff/oasdiff) on PATH
- For the .NET path: the `dotnet` SDK, and `nswag` for generated clients
- Optional LLM: `ANTHROPIC_API_KEY` for Claude, or a local Ollama

## Status

MVP, working end to end for the generated path, with an honest lower-confidence
path for manual clients. Per-API baselines are committed to the repo so it works
the same locally and in ephemeral CI runners. Next milestone: a GitHub Action /
Azure DevOps pipeline that opens the PR from the applied fix.
