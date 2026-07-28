# How it works

A single pass, step by step.

## The flow

```text
          OpenAPI Contract
                 |
                 v
          Current snapshot
                 |
                 v
              oasdiff  <----  Previous snapshot (committed baseline)
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

## Step by step

1. **Read the contract.** Download the current Swagger/OpenAPI and compare it
   against the committed baseline snapshot with oasdiff. If nothing changed, or
   nothing is breaking, stop early. This baseline comparison is why APIHealer
   isn't a linter: it reacts to *changes over time*, not the current spec alone.

2. **Decide the client type.** The `ClientClassifier` inspects the project:
   generated (a regenerable client like NSwag/Kiota), manual (hand-written), or
   none. This sets how much can be proven — see [Verification](./Verification.md).

3. **Regenerate & build** (generated path). Regenerate the client from the new
   contract and compile. The compiler errors pinpoint every place your code
   used what changed.

4. **Repair.** The configured LLM adapts only the affected code, from the
   compiler errors (generated) or the contract diff (manual).

5. **Verify.** Recompile to confirm the fix. The result reports the verification
   level, the evidence, and what a passing build still can't prove.

## Multiple APIs in one project

One project often consumes several APIs. Each gets its own baseline, keyed by a
name, so their snapshots never collide:

```bash
apihealer --path . --name orders   --swagger-url http://internal/orders/swagger.json
apihealer --path . --name payments --swagger-url https://api.stripe.com/openapi.json
apihealer --path . --list-apis
```

## Local vs. CI

The mechanics are identical; only who commits the baseline differs. Locally you
commit when you choose; in CI the pipeline does. Because baselines live in the
repo, a clean CI runner has everything it needs after a `git clone`. When a
breaking change is remediated, the updated baseline travels in the same PR as
the fix — so git is both the persistence and the audit trail of how each
contract evolved.
