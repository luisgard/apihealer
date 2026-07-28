# APIHealer testbench

A tiny local setup to exercise APIHealer end to end against real .NET code,
covering both client kinds: **generated (NSwag)** and **manual**.

## What's here

- `OrdersApi/` -- a provider API (`GET /orders/{id}`) with Swashbuckle. A
  `CONTRACT_VERSION` env var switches between the v1 and v2 shapes to simulate a
  provider breaking change.
- `Client.NSwag/` -- a consumer whose client is **generated** by NSwag. Business
  code in `OrderService.cs` reads the v1 fields.
- `Client.Manual/` -- a consumer with a **hand-written** `HttpClient` + DTO. No
  generator.
- `contracts/` -- pre-captured `swagger-v1.json` and `swagger-v2.json`, so you
  can test the diff even without running the API.

## The breaking change

```jsonc
// v1                                  // v2
{ "orderId": 1,                        { "orderId": 1,
  "customerId": 123,     -- removed -->  "customer": { "id": 123 },
  "status": "pending" }  -- renamed -->  "state": "pending" }
```

## Prerequisites

- .NET 8 SDK (`dotnet --version`)
- oasdiff on PATH
- NSwag CLI on PATH for the generated case (`dotnet tool install -g NSwag.ConsoleCore`)
- APIHealer installed (`pip install -e .` from the apihealer folder)

---

## Scenario A -- generated client (NSwag), the reliable path

1. Run the API on v1 and generate the first client:

   ```bash
   cd OrdersApi
   dotnet run --urls http://localhost:5080        # leave running
   ```

   In another terminal:

   ```bash
   cd Client.NSwag
   nswag run nswag.json      # generates GeneratedClient.cs from v1
   dotnet build              # should succeed
   ```

2. Establish the APIHealer baseline against v1:

   ```bash
   apihealer --path ./Client.NSwag \
             --swagger-url http://localhost:5080/swagger/v1/swagger.json
   ```

3. Switch the provider to v2 (the breaking change):

   ```bash
   # stop the API, then:
   CONTRACT_VERSION=2 dotnet run --urls http://localhost:5080
   # PowerShell: $env:CONTRACT_VERSION=2; dotnet run --urls http://localhost:5080
   ```

4. Run APIHealer with a fix. It should detect the break, regenerate the client,
   let the compiler flag `OrderService.cs`, fix it with the LLM, and recompile
   to verify:

   ```bash
   APIHEALER_LLM=ollama apihealer --path ./Client.NSwag \
       --swagger-url http://localhost:5080/swagger/v1/swagger.json \
       --apply --report md --report-out nswag-report.md
   ```

   Expected: classified `generated`, verification `build`, high confidence, and
   `OrderService.cs` adapted to read `order.Customer.Id` and `order.State`.

---

## Scenario B -- manual client, the honest-but-limited path

1. Baseline against v1 (API still on v1, or use the captured contract):

   ```bash
   apihealer --path ./Client.Manual \
             --swagger-url http://localhost:5080/swagger/v1/swagger.json
   ```

2. Switch the API to v2 (as above), then run with a fix:

   ```bash
   APIHEALER_LLM=ollama apihealer --path ./Client.Manual \
       --swagger-url http://localhost:5080/swagger/v1/swagger.json \
       --apply --report md --report-out manual-report.md
   ```

   Expected: classified `manual`, verification `syntax_only` (or `none` if
   dotnet is absent), medium/low confidence, and an explicit warning that a
   passing build does not prove the contract adaptation is complete.

---


## Watching multiple APIs in one project

Give each API a name so their baselines don't collide:

```bash
apihealer --path ./Client.NSwag --name orders   --swagger-url http://localhost:5080/swagger/v1/swagger.json
apihealer --path ./Client.NSwag --name payments --swagger-url https://api.stripe.com/openapi.json
```

Baselines are stored per name under `.apihealer/<name>/contract.json` and are
meant to be committed, so CI runners (which start clean) share the same
baseline. List what a project watches with `apihealer --path . --list-apis`.

## Testing without running the API

You can point `--swagger-url` at a local file server serving `contracts/`:

```bash
cd contracts && python -m http.server 8080
# then in another terminal, baseline against v1 and re-run against v2 by
# swapping which file the server exposes (or serve both and change the URL).
```

The point of the two clients is to *see the difference*: the generated path
gets compiler-verified high confidence; the manual path gets an honest,
lower-confidence result with the residual risks spelled out.
