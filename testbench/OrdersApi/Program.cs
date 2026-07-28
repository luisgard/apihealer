// OrdersApi - a tiny provider API used to test APIHealer end to end.
//
// It exposes GET /orders/{id}. Swashbuckle publishes the OpenAPI spec at
// /swagger/v1/swagger.json, generated FROM this code, so the contract is
// always truthful.
//
// To simulate a provider breaking change, set the env var CONTRACT_VERSION=2
// before running. v1 and v2 return different shapes:
//
//   v1: { "orderId": 1, "customerId": 123, "status": "pending" }
//   v2: { "orderId": 1, "customer": { "id": 123 }, "state": "pending" }
//
// Run v1:  dotnet run
// Run v2:  CONTRACT_VERSION=2 dotnet run   (PowerShell: $env:CONTRACT_VERSION=2; dotnet run)

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();
app.UseSwagger();
app.UseSwaggerUI();

var version = Environment.GetEnvironmentVariable("CONTRACT_VERSION") ?? "1";

if (version == "2")
{
    // v2 contract: nested customer + renamed field (status -> state).
    app.MapGet("/orders/{id}", (int id) => new OrderV2(
        OrderId: id,
        Customer: new CustomerRef(Id: 123),
        State: "pending"));
}
else
{
    // v1 contract: flat fields.
    app.MapGet("/orders/{id}", (int id) => new OrderV1(
        OrderId: id,
        CustomerId: 123,
        Status: "pending"));
}

app.Run();

// v1 shape
record OrderV1(int OrderId, int CustomerId, string Status);

// v2 shape
record OrderV2(int OrderId, CustomerRef Customer, string State);
record CustomerRef(int Id);
