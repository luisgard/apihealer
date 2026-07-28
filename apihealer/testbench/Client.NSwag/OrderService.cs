// Business code that CONSUMES the NSwag-generated client.
//
// This is the code APIHealer must repair. When the contract changes and the
// client is regenerated, the generated DTO changes shape and THIS file stops
// compiling -- which is exactly the compiler signal APIHealer relies on.
//
// With the v1 contract, the generated Order type has: OrderId, CustomerId, Status.
// After regenerating against v2, those become: OrderId, Customer.Id, State.
// So the two reads below (CustomerId, Status) will fail to compile under v2,
// pointing APIHealer at the exact lines to fix.

using Client.NSwag.Generated;

namespace Client.NSwag;

public class OrderService
{
    private readonly IOrdersClient _client;

    public OrderService(IOrdersClient client) => _client = client;

    public async Task<string> DescribeOrderAsync(int id)
    {
        var order = await _client.OrdersAsync(id);

        // These two reads encode the v1 contract into business logic:
        var customerId = order.CustomerId;   // v2: moves to order.Customer.Id
        var status = order.Status;           // v2: renamed to order.State

        return $"Order {order.OrderId} for customer {customerId} is {status}";
    }
}
