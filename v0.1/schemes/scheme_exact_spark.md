# Exact Payment Scheme for Spark

This document specifies the `exact` payment scheme for the x402 protocol on Spark.

This scheme facilitates payments of a specific amount over Bitcoin using Lightning or Spark.

## Scheme Name

`exact`

## Protocol Flow

The protocol flow for `exact` on Spark is client-driven.

1. **Client** makes an HTTP request to a **Resource Server**.  
2. **Resource Server** responds with a `402 Payment Required` status. The response body contains the `paymentRequirements` for the `exact` scheme  
   - In addition, the `extra` field in the requirements may contain a **lightningInvoice** or a **depositAddress** which both resolve to the Spark address specified in `payTo`.  
3. **Client** proceeds with one of: (1) directly sending Bitcoin to the **sparkAddress** in the payTo field, (2) paying the **lightningInvoice**, or (3) transferring Bitcoin over L1 to the **depositAddress**.  
4. **Client** sends a new HTTP request to the resource server with the `X-PAYMENT` header containing the details of the payment made.  
5. **Resource Server** receives the request and verifies the payment.  
6. **Resource Server** grants the **Client** access to the resource in its response.

## `PaymentRequirements` for `exact`

In addition to the standard x402 `PaymentRequirements` fields, the `exact` scheme on Spark may contain the following inside the `extra` field:

```json
{
  "scheme": "exact",
  "network": "bip122:000000000019d6689c085ae165831e93",
  "maxAmountRequired": "1000",
  "asset": "BTC",
  "payTo": "spark1...",
  "resource": "https://example.com/weather",
  "description": "Access to protected content",
  "mimeType": "application/json",
  "maxTimeoutSeconds": 60,
  "outputSchema": null,
  "extra": {
    "lightningInvoice": "lnbc1...",
    "depositAddress": "bc1..."
  }
}
```

* `asset`: The currency to be paid (e.g., "BTC").  
* `maxAmountRequired`: The amount to be paid in satoshis.  
* `extra.lightningInvoice`: An optional Bitcoin Lightning invoice which resolves to the specified Spark address.  
* `extra.depositAddress`: An optional Bitcoin L1 address which resolves to the specified Spark address.

## `X-PAYMENT` Header Payload

The `X-PAYMENT` header is base64 encoded and sent in the request from the client to the resource server when paying for a resource.

Once decoded, the `X-PAYMENT` header is a JSON string with the following properties:

```json
{
  "x402Version": 1,
  "scheme": "exact",
  "network": "bip122:000000000019d6689c085ae165831e93",
  "payload": {
    "paymentType": "SPARK" | "LIGHTNING" | "L1",
    "transfer_id": "...",  // Spark (unset if not paid over Spark)
    "preimage": "...",     // Lightning (unset if not paid over Lightning)
    "txid": "..."          // L1 (unset if not paid over Bitcoin L1)
  }
}
```

The `payload` field contains the details of the payment made by the client, which will vary based on the `paymentType`. Regardless of the payment type, the server will be able to query the Spark network and obtain the transfer ID once the payment is finalized.

For Spark and Lightning payments, the resource server must acknowledge the payment immediately. For L1 deposits, the resource server may choose to wait for up to 3 confirmations before acknowledging that the payment was received.

## `X-PAYMENT-RESPONSE` Header Payload

The `X-PAYMENT-RESPONSE` header is base64 encoded and returned to the client from the resource server.

Once decoded, the `X-PAYMENT-RESPONSE` is a JSON string with the following properties:

```json
{
  "success": true | false,
  "network": "bip122:000000000019d6689c085ae165831e93",
  "transfer_id": "hex-encoded identifier for the Spark transfer"
}
```
