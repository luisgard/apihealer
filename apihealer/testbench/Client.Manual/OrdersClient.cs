// A HAND-WRITTEN client. No generator, no nswag.json.
//
// This is the MANUAL case for APIHealer. When the provider's contract changes
// (v1 -> v2), NOTHING here stops compiling: the DTO below still maps the old
// field names via [JsonPropertyName]. The code is valid C# that silently
// deserializes into the wrong shape at runtime.
//
// That's the whole point of the manual path: the compiler gives no signal, so
// APIHealer must locate the impact from the contract diff and report LOWER
// confidence, warning that a passing build does not prove correctness.

using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace Client.Manual;

// Hand-written DTO encoding the v1 contract.
public class OrderDto
{
    [JsonPropertyName("orderId")]
    public int OrderId { get; set; }

    [JsonPropertyName("customerId")]   // v2: this field is gone (nested under customer)
    public int CustomerId { get; set; }

    [JsonPropertyName("status")]       // v2: renamed to "state"
    public string Status { get; set; } = "";
}

public class OrdersClient
{
    private readonly HttpClient _http;

    public OrdersClient(HttpClient http) => _http = http;

    public async Task<string> DescribeOrderAsync(int id)
    {
        var order = await _http.GetFromJsonAsync<OrderDto>($"/orders/{id}");
        if (order is null) return "not found";

        // Reads the v1 fields. Under v2 these still compile but come back empty.
        return $"Order {order.OrderId} for customer {order.CustomerId} is {order.Status}";
    }
}
