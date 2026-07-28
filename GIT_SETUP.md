# Uploading APIHealer to GitHub

This folder is your repository root. It contains:

- `apihealer/` -- the tool (Python)
- `testbench/` -- local .NET projects to test it end to end
- `.gitignore` -- ignores build artifacts, but KEEPS the contract baselines

Note: `.apihealer/<name>/contract.json` baselines are meant to be committed --
that's what lets CI runners (which start clean) share the same baseline. Only
the transient `contract_incoming.json` download is ignored.

## 1. Create the repository on GitHub

Go to github.com, click **New repository**, name it `apihealer`, choose
**Private** (this started from work context; you can make it public later),
and do NOT add a README/`.gitignore`/license (you already have them).

## 2. Push from your machine

Open a terminal in this folder (the one containing `apihealer/` and
`testbench/`) and run:

```bash
git init
git add .
git commit -m "Initial commit: APIHealer contract remediation tool + .NET testbench

Contract-driven API remediation for consumers:
- OpenAPI breaking-change detection via oasdiff against a per-API baseline
- client classification (generated / manual / none) with evidence
- .NET adapter: coordinator over classifier + strategies + toolchain
- compiler-backed remediation loop for generated clients (NSwag/Kiota/openapi-generator)
- LLM-assisted remediation for manual clients, with honest lower confidence
- transactional file writes with rollback
- pluggable LLM providers (Claude, local Ollama)
- structured VerificationReport with Markdown/JSON output for CI/CD
- per-API baselines committed to the repo (works in ephemeral CI runners)
- testbench: OrdersApi + NSwag and manual clients, with v1/v2 contracts"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/apihealer.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username. Copy the exact `remote add`
URL from the page GitHub shows you after creating the empty repo.

## 3. First push authentication

The first `git push` will ask you to authenticate. GitHub no longer accepts a
plain password: it will either open the browser or ask for a Personal Access
Token (Settings -> Developer settings -> Personal access tokens on GitHub).
GitHub Desktop handles this for you if you prefer buttons over the terminal.

## Prefer GitHub Desktop?

Download from desktop.github.com, open it, drag this folder in, name it
`apihealer`, and click **Publish repository** (uncheck "public" to keep it
private). No commands needed.
