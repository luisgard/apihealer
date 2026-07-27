# APIHealer

Detects breaking changes in the Swagger/OpenAPI spec of a consumed API and auto-heals your downstream code. As a consumer, you run it locally and review the generated fix.


## The Idea

When an upstream API changes—whether third-party or an internal team—an agent detects the change, patches your code, and leaves a Pull Request ready for review, instead of breaking your production environment.

## Architecture

Two halves with a clearly defined boundary:

Core (apihealer/core): Language and OS agnostic. It takes the path, detects the language, downloads the Swagger, diffs it with oasdiff, and orchestrates the flow. It operates strictly on the OpenAPI contract, not your source code, making it universally applicable.
Adapters (apihealer/adapters): Language-specific logic. Currently only DotNetAdapter. Each adapter implements the base.py interface and invokes native language toolchains (e.g., nswag, dotnet) as external processes: Python orchestrates, native tools execute.
Adding a new language = writing an adapter that fulfills the interface and registering it. The core remains untouched.

## Two Axes of Extensibility
Language Adapters (adapters/): How to patch the code. Today: .NET.
Contract Sources (core/contract_source.py): Where the API shape comes from. Today: SwaggerSource (published spec). Prepared but pending: InferredSource, which infers the shape by probing the actual endpoints, useful for legacy APIs without Swagger. Both axes scale without touching the core.

## Flow
Receive the project path.
Detect language → select adapter.
Receive the Swagger URL.
Download and diff against the previous snapshot (oasdiff). If unchanged or no breaking changes, exit cheaply here.
If breaking changes exist, the adapter proposes (or applies) the fix.
For generated clients (NSwag/Refit/Kiota), the most reliable strategy is: regenerate the client from the new Swagger spec → compile → the compiler errors act as the exact list of what to fix and where.

## Requirements
Python 3.10+
oasdiff in your PATH (single binary, cross-platform).
For the .NET adapter: the dotnet SDK and, if using NSwag, nswag in your PATH.
## Usage
install (from the project folder)pip install -e .
run interactivelyapihealer# or pass data via argumentsapihealer --path /path/to/my/project --swagger-url https://upstream-team/swagger/v1/swagger.json
The first run establishes the baseline. 
Run it again after the provider makes a change to detect and patch.

## Status
MVP under active development. Currently working: The full core flow → detection → diff → adapter delegation, with safe failure handling (if it can't fix it, it alerts and touches nothing; the baseline only advances when the change is successfully resolved).

Pending (the final 10% polish):

Automatic business-logic patching via LLM based on compiler errors (currently, the adapter reports errors with precision; applying the fix is pending).
Git / Azure DevOps integration to open the Pull Request.
Support for manual clients (the hard path) and other languages.
InferredSource for APIs without Swagger (abstraction is ready).
Authentication for protected Swaggers and webhook-driven triggers.