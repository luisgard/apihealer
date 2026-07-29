# Verification

APIHealer is **verification-aware**: it never treats "I changed the code" as
"I know the code is right." Every remediation carries a `VerificationReport`
that states what was actually checked and what a passing check still cannot
prove. This document explains that model in depth.

## Why this is the core idea

Most "AI fixes your code" tools stop at *a change was produced*. The hard,
valuable question is the next one: **how much can you trust it?** APIHealer's
answer is graded by how much deterministic evidence backs the fix, not by how
confident the model sounds.

## Generated vs. manual: why the client type decides everything

The client type sets the ceiling on how much can be proven.

### Generated clients (NSwag / Kiota / openapi-generator)

Generated clients encode the contract into **types**. When the contract changes,
regenerating the client changes those types, and any code using the old shape
**stops compiling**. That compiler failure is a precise, deterministic map of
exactly what broke and where.

```text
OpenAPI contract
      |
      v
generated DTO types      <- regeneration updates these
      |
      v
compiler errors          <- pinpoints every broken usage
      |
      v
targeted fix + recompile <- the fix is verified, not assumed
```

Because the compiler both **finds** the impact and **verifies** the fix, a
generated remediation can honestly earn high confidence.

### Manual clients (hand-written / Refit)

A hand-written client encodes the contract **loosely** — for example a DTO with
`[JsonPropertyName("customerId")]`. When the contract changes, nothing stops
compiling: the code is still valid C# that now silently deserializes into the
wrong shape at runtime.

```text
OpenAPI contract
      |
      v
manual JSON mapping      <- unchanged, still compiles
      |
      x
(no compiler signal)     <- the impact is invisible to the build
```

Here APIHealer must locate the impact from the **contract diff** and let the LLM
adapt the code. It compiles if it can, but a passing compile only proves syntax —
so confidence is medium/low **by design**, and the report says why.

## The VerificationReport

Every result carries this structure:

```text
RemediationResult
   ├── files_changed
   ├── confidence            (0.0–1.0)
   ├── applied               (was it written to disk?)
   └── VerificationReport
          ├── level          (build / syntax_only / none / build_failed)
          ├── evidence       (what was actually checked)
          └── remaining_risks (what a pass does NOT prove)
```

`applied` and `verification` are **independent axes**. "I wrote it" is a
side-effect fact; "I can prove it" is an epistemic one. A manual fix can be
`applied: true` with `verification.level: syntax_only` — written, but not
proven. Keeping them separate is the whole point.

## Verification levels

| Level | Meaning | Typical confidence |
|---|---|---|
| `build` | Regenerated and recompiled successfully | High (~0.85–0.9) |
| `inferred_build` | Manual client: inferred the new shape, applied it, and it compiles | Medium (~0.65) |
| `syntax_only` | Compiled, but the compiler can't confirm the contract mapping | Medium (~0.5) |
| `none` | Couldn't verify (no toolchain, or detection-only) | Low |
| `build_failed` | A fix was attempted but the project doesn't compile | Low — needs human review |

### On `inferred_build` — being bold without lying

For a manual client there's no compiler signal to *find* the impact, but that
doesn't mean APIHealer should refuse to act. Instead it makes a best-effort
**inference** from the contract diff — creating new DTOs, renesting fields,
renaming — applies it, and compiles. The compiler then proves the types and
references are consistent. What it *cannot* prove is that the inferred mapping
is semantically right (that the new `customer.id` really is the old
`customerId`). So `inferred_build` sits deliberately between `build` and
`syntax_only`: APIHealer did real work and verified compilation, and says
plainly that the mapping is an inference to confirm. The boldness is made
visible and measurable, not hidden.

## Naming the tiers

The UI names the three outcomes so the state is clear at a glance:

- **Verified remediation** — generated client, regenerated and recompiled.
- **Inferred remediation** — manual client, inference applied and it compiles.
- **Suggested remediation** — manual client, a change was written but not
  compile-verified.

## Explainable confidence

The confidence number is **not** a magic constant. It's the sum of named
factors, each tied to a real signal, and the breakdown is shown on every result
(and in the report). For example, an inferred manual remediation:

```text
+0.40  base: manual client (no compiler signal to find impact)
+0.15  remediation inferred from the contract diff and applied
+0.30  recompiled successfully: types and references consistent
-0.20  semantic mapping was inferred, not proven
-----
 0.65  total
```

This answers "why 0.65 and not 0.70?" directly. The factors are honest signals
the system genuinely has today; finer inputs (like field-name similarity between
the removed and added properties) can be added later as real measurements, not
invented weights.

## Residual risks: what a passing build still can't prove

Even a compiler-verified generated fix does **not** prove:

- **Runtime serialization** behaves as expected;
- **business logic / validation** semantics are preserved;
- **new enum values or nullability changes** don't alter behavior.

APIHealer lists these on every result so the human reviewer knows exactly what
to check. This is the difference between a tool that hides its limits and one
that hands you the receipts.

## Fail closed

When APIHealer cannot establish enough evidence, it reports the uncertainty
instead of applying a confident-looking guess. Low confidence is a feature: it's
the tool refusing to overclaim.
