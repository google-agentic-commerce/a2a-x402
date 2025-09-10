import { A2AClient } from "@a2a-js/sdk/client";
import { v4 as uuidv4 } from "uuid";
import { Wallet, hexlify, randomBytes, JsonRpcProvider } from "ethers";

const X402_EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1";
const X402_STATUS_KEY = "x402.payment.status";
const X402_REQUIRED_KEY = "x402.payment.required";
const X402_PAYLOAD_KEY = "x402.payment.payload";

// (Removed mock payload helper; the example uses a real EIP-3009 signature below)

async function main() {
  const cardUrl = "http://localhost:10000/.well-known/agent-card.json";
  // Always include activation header on all client requests
  const fetchWithExtension = (input, init = {}) => {
    const headers = { ...(init.headers || {}), "X-A2A-Extensions": X402_EXTENSION_URI };
    return fetch(input, { ...init, headers });
  };
  const client = await A2AClient.fromCardUrl(cardUrl, { fetchImpl: fetchWithExtension });

  // Send initial message
  const params = {
    message: {
      messageId: uuidv4(),
      role: "user",
      parts: [{ kind: "text", text: "Hello, merchant!" }],
      kind: "message",
    },
    configuration: {
      blocking: true,
      acceptedOutputModes: ["text/plain"],
    },
  };

  const createdResp = await client.sendMessage(params);
  const createdTask = createdResp?.result;
  console.log("Created Task:", createdTask?.id, createdTask?.status?.state);

  // Inspect for payment-required in status.message.metadata
  const statusMessage = createdTask?.status?.message;
  const metadata = statusMessage?.metadata || {};
  if (metadata[X402_STATUS_KEY] !== "payment-required") {
    console.log("No payment required. Exiting.");
    return;
  }

  const paymentRequired = metadata[X402_REQUIRED_KEY];
  // Build a real EIP-3009 signature with a local payer key
  const payerKey = process.env.CLIENT_PRIVATE_KEY;
  if (!payerKey) {
    throw new Error("CLIENT_PRIVATE_KEY env var is required to sign payment.");
  }
  // Derive chainId from RPC (same approach as server)
  const rpcUrl = process.env.RPC_URL;
  if (!rpcUrl) {
    throw new Error("RPC_URL env var is required to determine chainId.");
  }
  const net = await new JsonRpcProvider(rpcUrl).getNetwork();
  const chainId = Number(net.chainId);
  const wallet = new Wallet(payerKey);
  const selected = paymentRequired.accepts[0];
  // Normalize addresses to lowercase (ethers EIP-712 encoding accepts lowercase)
  const asset = String(selected.asset).trim().toLowerCase();
  const payTo = String(selected.payTo).trim().toLowerCase();
  const nonce = hexlify(randomBytes(32));
  const validAfter = 0;
  const validBefore = Math.floor(Date.now() / 1000) + (selected.maxTimeoutSeconds || 600);
  // Prefer server-provided domain if available
  const serverDomain = selected.extra && selected.extra.domain;
  const domain = serverDomain && serverDomain.verifyingContract?.toLowerCase() === asset
    ? { ...serverDomain, chainId: Number(serverDomain.chainId) }
    : {
        name: "USD Coin",
        version: "2",
        chainId,
        verifyingContract: asset,
      };
  const types = {
    TransferWithAuthorization: [
      { name: "from", type: "address" },
      { name: "to", type: "address" },
      { name: "value", type: "uint256" },
      { name: "validAfter", type: "uint256" },
      { name: "validBefore", type: "uint256" },
      { name: "nonce", type: "bytes32" },
    ],
  };
  const message = {
    from: wallet.address,
    to: payTo,
    value: selected.maxAmountRequired,
    validAfter,
    validBefore,
    nonce,
  };
  const signature = await wallet.signTypedData(domain, types, message);
  const paymentPayload = {
    x402Version: 1,
    scheme: selected.scheme,
    network: selected.network,
    payload: {
      from: message.from,
      payTo: message.to,
      asset,
      value: message.value,
      validAfter: message.validAfter,
      validBefore: message.validBefore,
      nonce: message.nonce,
      signature,
    },
  };

  // Submit payment payload with correlation to original taskId
  const submissionResp = await client.sendMessage({
    message: {
      messageId: uuidv4(),
      taskId: createdTask.id,
      role: "user",
      parts: [{ kind: "text", text: "Here is the payment authorization." }],
      kind: "message",
      metadata: {
        [X402_STATUS_KEY]: "payment-submitted",
        [X402_PAYLOAD_KEY]: paymentPayload,
      },
    },
    configuration: {
      blocking: true,
      acceptedOutputModes: ["text/plain"],
    },
  });

  const submission = submissionResp?.result;
  console.log("After payment submission, task state:", submission?.status?.state);
  const finalMeta = submission?.status?.message?.metadata || {};
  console.log("Payment status:", finalMeta[X402_STATUS_KEY]);
  if (Array.isArray(finalMeta["x402.payment.receipts"])) {
    console.log("Receipt:", finalMeta["x402.payment.receipts"][0]);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});



