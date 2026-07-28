# Architecture

APIHealer is built so that adding a language or a contract source never touches
the core. This document covers the structure and the extension points.

## Two halves with a clean boundary

- **Core** (`apihealer/core`): language- and OS-agnostic. It asks for the path,
  detects the language, downloads the contract, diffs it with oasdiff against a
  baseline, and orchestrates. It works on the OpenAPI contract, not on your
  code, so it serves any language.
- **Adapters** (`apihealer/adapters`): the language-specific parts. Each adapter
  fulfills the contract in `base.py` and invokes the language's native tools
  (nswag, dotnet, ...) as external processes. Today: `.NET`.

## Design philosophy

> Python orchestrates; native tools do the work; the compiler verifies; the
> LLM only proposes.

No adapter executes your project's code directly — it shells out to the real
toolchain and reads the output. Determinism where it exists; the LLM only fills
the gap the tools can't.

## The .NET adapter is a thin coordinator

After separating responsibilities, `DotNetAdapter` just detects, classifies,
picks a strategy, and delegates:

```text
DotNetAdapter (coordinator)
   ├── ClientClassifier        -> generated / manual / none, with evidence
   ├── STRATEGY_REGISTRY       -> ClientKind -> strategy (plugin map)
   │      ├── GeneratedFixStrategy
   │      └── ManualFixStrategy
   ├── DotNetToolchain         -> all native calls (build, regenerate, parse)
   └── Generators (pluggable)  -> NSwag / Kiota / openapi-generator
```

Each piece has one responsibility:

- **ClientClassifier** — the most heuristic, fallible part, isolated so it can be
  tested on real projects without starting the engine. Generator detection reads
  manifests (`.csproj`, config files), never code comments, to avoid false
  positives.
- **Strategies** — the two fix algorithms. The philosophical difference ("what
  the compiler guarantees") is encoded as *structure*: `GeneratedFixStrategy`
  verifies with the compiler and can claim high confidence; `ManualFixStrategy`
  structurally cannot.
- **DotNetToolchain** — the single place that invokes native tools. A
  `FakeToolchain` makes strategies testable without `dotnet` installed.
- **Generators** — registered in a list; adding Kiota or openapi-generator is
  writing a class, not editing the adapter.

## Two axes of extensibility

- **Language adapters** (`adapters/`): *how* to remediate the code. The mold
  (`Classifier` + `Strategy` + `Toolchain`) is ready to copy for a `JavaAdapter`,
  `PythonAdapter`, etc.
- **Contract sources** (`core/contract_source.py`): *where* the API shape comes
  from. Today: `SwaggerSource`. Planned: `InferredSource` (derives a partial
  contract from observed endpoint responses), then GraphQL, gRPC.

Both grow without touching the core.

## Safety mechanics

- **Transactional writes** (`core/file_tx.py`): a multi-file fix that fails
  midway rolls back, so the working tree never ends up half-changed.
- **Per-API baselines** (`core/snapshot_store.py`): each watched API stores its
  baseline under `.apihealer/<name>/contract.json`, committed to the repo. This
  is what makes it work the same locally and in ephemeral CI runners — the runner
  clones the repo and the baseline is already there.

## Pluggable LLM

`core/llm.py` defines a minimal provider interface; `core/llm_providers.py`
implements Claude and local Ollama, chosen by the `APIHEALER_LLM` env var. Keys
are read from the environment, never from code. Local providers keep your code
on your machine.
