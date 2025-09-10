import express from "express";
import { v4 as uuidv4 } from "uuid";
import { JsonRpcProvider, Wallet, Contract, Signature, verifyTypedData } from "ethers";
import { DefaultRequestHandler, InMemoryTaskStore } from "@a2a-js/sdk/server";
import { A2AExpressApp } from "@a2a-js/sdk/server/express";

// x402 extension constants per spec
const X402_EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1";
const X402_STATUS_KEY = "x402.payment.status";
const X402_REQUIRED_KEY = "x402.payment.required";
const X402_PAYLOAD_KEY = "x402.payment.payload";
const X402_RECEIPTS_KEY = "x402.payment.receipts";

// Merchant/token configuration (env configurable)
const MERCHANT_WALLET = process.env.MERCHANT_PRIVATE_KEY ? new Wallet(process.env.MERCHANT_PRIVATE_KEY) : undefined;
const MERCHANT_ADDRESS = MERCHANT_WALLET ? MERCHANT_WALLET.address : undefined; // the payee/recipient
const ASSET_ADDRESS = process.env.ASSET_ADDRESS || "0x036CbD53842c5426634e7929541eC2318f3dCF7e"; // usdc on base sepolia
const X402_NETWORK = process.env.X402_NETWORK || "base-sepolia"; // e.g., "base" or "base-sepolia"
const PRICE_USDC = process.env.PRICE_USDC || "1"; // decimal string, e.g., "1" or "1.50"
const PRICE_ATOMIC = process.env.PRICE_ATOMIC; // optional override in atomic units string
const MAX_TIMEOUT_SECONDS = parseInt(process.env.MAX_TIMEOUT_SECONDS || "600", 10);

// On-chain settlement configuration (set these for a fully functional demo)
const RPC_URL = process.env.RPC_URL; // e.g. Base mainnet/sepolia RPC
const MERCHANT_PRIVATE_KEY = process.env.MERCHANT_PRIVATE_KEY; // merchant signer key

// Minimal USDC v2 EIP-3009 ABI
const USDC_EIP3009_ABI = [
  "function transferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce,uint8 v,bytes32 r,bytes32 s) external returns (bool)"
];
const ERC20_METADATA_ABI = [
  "function name() view returns (string)",
  "function version() view returns (string)",
  "function decimals() view returns (uint8)"
];

async function getDomain(provider, tokenAddress) {
  const net = await provider.getNetwork();
  const token = new Contract(tokenAddress, ERC20_METADATA_ABI, provider);
  let name = "USD Coin";
  let version = "2";
  try {
    name = await token.name();
  } catch {}
  try {
    const v = await token.version();
    if (typeof v === "string" && v.length > 0) version = v;
  } catch {}
  return {
    name,
    version,
    chainId: Number(net.chainId),
    verifyingContract: tokenAddress,
  };
}

function decimalToAtomic(decimalStr, decimals) {
  const [whole, frac = ""] = String(decimalStr).split(".");
  const fracPadded = (frac + "0".repeat(decimals)).slice(0, decimals);
  const combined = `${whole}${fracPadded}`.replace(/^0+/, "");
  return combined.length ? combined : "0";
}

async function getTokenDecimals(provider, tokenAddress, fallbackDecimals) {
  try {
    const token = new Contract(tokenAddress, ERC20_METADATA_ABI, provider);
    const d = await token.decimals();
    const n = Number(d);
    if (!Number.isNaN(n) && n > 0 && n < 255) return n;
  } catch {}
  return fallbackDecimals;
}

// Create a minimal AgentCard advertising the x402 extension
const agentCard = {
  name: "JS Merchant Agent",
  description: "Minimal merchant that requires x402 payment for a service",
  url: "http://localhost:10000",
  version: "0.1.0",
  defaultInputModes: ["text", "text/plain"],
  defaultOutputModes: ["text", "text/plain"],
  capabilities: {
    streaming: true,
    extensions: [
      {
        uri: X402_EXTENSION_URI,
        description: "Supports payments using the x402 protocol for on-chain settlement.",
        required: true,
      },
    ],
  },
};

// Simple executor that triggers payment for any request
class MerchantExecutor {
  constructor(provider, signer) {
    this.provider = provider;
    this.signer = signer;
  }

  async execute(requestContext, eventBus) {
    const { taskId, contextId, userMessage } = requestContext;
    const meta = (userMessage && userMessage.metadata) || {};

    console.log("[server] execute start", {
      taskId,
      contextId,
      status: meta[X402_STATUS_KEY] || null,
      hasPayload: Boolean(meta[X402_PAYLOAD_KEY]),
    });

    if (meta[X402_STATUS_KEY] === "payment-submitted" && taskId) {
      console.log("[server] payment-submitted received", {
        taskId,
        contextId,
      });

      // Extract EIP-3009 fields from payload
      const payload = meta[X402_PAYLOAD_KEY];
      const selected = payload?.payload || {};
      const asset = selected.asset || ASSET_ADDRESS;
      const from = selected.from;
      const to = selected.payTo || MERCHANT_ADDRESS;
      const value = selected.value;
      const validAfter = selected.validAfter || 0;
      const validBefore = selected.validBefore;
      const nonce = selected.nonce;
      const sigHex = selected.signature;
      if (!from || !to || !value || !validBefore || !nonce || !sigHex) {
        console.error("[server] missing required EIP-3009 fields in payload");
        eventBus.publish({
          kind: "status-update",
          taskId,
          contextId,
          status: {
            state: "failed",
            message: {
              kind: "message",
              role: "agent",
              parts: [{ kind: "text", text: "Payment verification failed: invalid payload." }],
              metadata: { [X402_STATUS_KEY]: "payment-failed" },
            },
            timestamp: new Date().toISOString(),
          },
          final: true,
        });
        eventBus.finished();
        return;
      }

      // Verify EIP-712 signature (USDC v2 EIP-3009 TransferWithAuthorization)
      const domain = await getDomain(this.provider, asset);
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
      const message = { from, to, value, validAfter, validBefore, nonce };

      let recovered;
      try {
        recovered = verifyTypedData(domain, types, message, sigHex);
      } catch (e) {
        console.error("[server] verifyTypedData error", e);
      }
      if (!recovered || recovered.toLowerCase() !== String(from).toLowerCase()) {
        console.error("[server] signature recovery mismatch", { recovered, from });
        eventBus.publish({
          kind: "status-update",
          taskId,
          contextId,
          status: {
            state: "failed",
            message: {
              kind: "message",
              role: "agent",
              parts: [{ kind: "text", text: "Payment verification failed: invalid signature." }],
              metadata: { [X402_STATUS_KEY]: "payment-failed" },
            },
            timestamp: new Date().toISOString(),
          },
          final: true,
        });
        eventBus.finished();
        return;
      }

      // Publish payment-pending before on-chain settlement
      eventBus.publish({
        kind: "status-update",
        taskId,
        contextId,
        status: {
          state: "working",
          message: {
            kind: "message",
            role: "agent",
            parts: [{ kind: "text", text: "Payment authorization verified. Settling on-chain..." }],
            metadata: { [X402_STATUS_KEY]: "payment-pending" },
          },
        },
        final: false,
      });
      console.log("[server] payment-pending published", { taskId });

      if (!this.provider || !this.signer) {
        console.error("[server] RPC_URL or MERCHANT_PRIVATE_KEY not set. Cannot settle on-chain.");
        eventBus.publish({
          kind: "status-update",
          taskId,
          contextId,
          status: {
            state: "failed",
            message: {
              kind: "message",
              role: "agent",
              parts: [{ kind: "text", text: "Settlement configuration missing (RPC_URL or MERCHANT_PRIVATE_KEY)." }],
              metadata: { [X402_STATUS_KEY]: "payment-failed" },
            },
            timestamp: new Date().toISOString(),
          },
          final: true,
        });
        eventBus.finished();
        return;
      }

      // Submit on-chain settlement: transferWithAuthorization
      const contract = new Contract(asset, USDC_EIP3009_ABI, this.signer);
      const sig = Signature.from(sigHex);
      const tx = await contract.transferWithAuthorization(
        from,
        to,
        value,
        validAfter,
        validBefore,
        nonce,
        sig.v,
        sig.r,
        sig.s
      );
      console.log("[server] settlement tx sent", { hash: tx.hash });
      const mined = await tx.wait();
      console.log("[server] settlement tx mined", { hash: mined?.hash });

      // Append receipts history
      const prevReceipts = requestContext?.task?.status?.message?.metadata?.[X402_RECEIPTS_KEY] || [];
      const receipt = {
        success: true,
        transaction: mined?.hash || tx.hash,
        network: X402_NETWORK,
        payer: from,
      };

      // Working update with completed payment and receipt
      eventBus.publish({
        kind: "status-update",
        taskId,
        contextId,
        status: {
          state: "working",
          message: {
            kind: "message",
            role: "agent",
            parts: [{ kind: "text", text: "Payment successful. Processing your request." }],
            metadata: {
              [X402_STATUS_KEY]: "payment-completed",
              [X402_RECEIPTS_KEY]: [...prevReceipts, receipt],
            },
          },
        },
        final: false,
      });
      console.log("[server] published working with payment-completed", { taskId });

      // Final completion (include payment metadata and receipts)
      eventBus.publish({
        kind: "status-update",
        taskId,
        contextId,
        status: {
          state: "completed",
          message: {
            kind: "message",
            role: "agent",
            parts: [{ kind: "text", text: "Payment successful. Your result is ready." }],
            metadata: {
              [X402_STATUS_KEY]: "payment-completed",
              [X402_RECEIPTS_KEY]: [...prevReceipts, receipt],
            },
          },
          timestamp: new Date().toISOString(),
        },
        final: true,
      });
      console.log("[server] published completed with receipt", receipt);
      eventBus.finished();
      return;
    }

    console.log("[server] publishing payment-required", { taskId, contextId });

    // Default path: require payment first — publish a Task and finish
    // Prepare EIP-712 domain for the token so the client can sign with the exact same fields
    let domainForClient = undefined;
    let tokenDecimals = 6;
    try {
      if (this.provider) {
        domainForClient = await getDomain(this.provider, ASSET_ADDRESS);
        tokenDecimals = await getTokenDecimals(this.provider, ASSET_ADDRESS, 6);
      }
    } catch (e) {
      console.warn("[server] failed to derive token domain; client will use defaults", e?.message || e);
    }

    eventBus.publish({
      kind: "task",
      id: taskId,
      contextId,
      status: {
        state: "input-required",
        message: {
          kind: "message",
          role: "agent",
          parts: [{ kind: "text", text: "Payment is required to generate the result." }],
          metadata: {
            [X402_STATUS_KEY]: "payment-required",
            [X402_REQUIRED_KEY]: {
              x402Version: 1,
              accepts: [
                {
                  scheme: "exact",
                  network: X402_NETWORK,
                  resource: "https://api.example.com/generate",
                  description: "Generate a response",
                  mimeType: "application/json",
                  outputSchema: {},
                  asset: ASSET_ADDRESS,
                  payTo: MERCHANT_ADDRESS,
                  maxAmountRequired: PRICE_ATOMIC || decimalToAtomic(PRICE_USDC, tokenDecimals),
                  maxTimeoutSeconds: MAX_TIMEOUT_SECONDS,
                  extra: { name: "USD Coin", version: 2, domain: domainForClient },
                },
              ],
            },
          },
        },
      },
    });
    eventBus.finished();
    console.log("[server] published input-required and finished", { taskId, contextId });
  }

  async cancelTask(taskId, eventBus) {
    // contextId is not available here; publish without it
    console.log("[server] cancelTask", { taskId });
    eventBus.publish({
      kind: "status-update",
      taskId,
      status: { state: "canceled", timestamp: new Date().toISOString() },
      final: true,
    });
    eventBus.finished();
    console.log("[server] cancellation published", { taskId });
  }
}

async function main() {
  const app = express();
  app.use(express.json());
  // Echo extension activation header on all responses
  app.use((req, res, next) => {
    res.setHeader("X-A2A-Extensions", X402_EXTENSION_URI);
    next();
  });

  const taskStore = new InMemoryTaskStore();
  const sharedProvider = RPC_URL ? new JsonRpcProvider(RPC_URL) : undefined;
  const sharedSigner = MERCHANT_PRIVATE_KEY && sharedProvider ? new Wallet(MERCHANT_PRIVATE_KEY, sharedProvider) : undefined;
  const executor = new MerchantExecutor(sharedProvider, sharedSigner);
  const requestHandler = new DefaultRequestHandler(agentCard, taskStore, executor);

  const a2a = new A2AExpressApp(requestHandler);
  a2a.setupRoutes(app);

  const port = 10000;
  app.listen(port, () => {
    console.log(`Merchant server listening on http://localhost:${port}`);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
