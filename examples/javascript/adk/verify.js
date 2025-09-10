import { JsonRpcProvider, Interface } from "ethers";

// Usage:
//   RPC_URL=https://... CHAIN_ID=84532 node verify.js 0xTRANSACTION_HASH
// or npm run verify -- 0xTRANSACTION_HASH (after setting env vars)

const ABI = [
  // Events
  "event Transfer(address indexed from, address indexed to, uint256 value)",
  "event Approval(address indexed owner, address indexed spender, uint256 value)",
  "event AuthorizationUsed(address indexed authorizer, bytes32 indexed nonce)",
  "event AuthorizationCanceled(address indexed authorizer, bytes32 indexed nonce)",
  // Function (for input decoding)
  "function transferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce,uint8 v,bytes32 r,bytes32 s)"
];

async function main() {
  const txHash = process.argv[2];
  if (!txHash) {
    console.error("Usage: npm run verify -- <txHash>");
    process.exit(1);
  }

  const rpcUrl = process.env.RPC_URL;
  if (!rpcUrl) {
    console.error("RPC_URL env var required");
    process.exit(1);
  }
  const provider = new JsonRpcProvider(rpcUrl);
  const [network, tx, receipt] = await Promise.all([
    provider.getNetwork(),
    provider.getTransaction(txHash),
    provider.getTransactionReceipt(txHash),
  ]);
  if (!receipt) {
    console.error("No receipt found for tx:", txHash);
    process.exit(1);
  }

  const iface = new Interface(ABI);
  console.log("Network:", network?.name, network?.chainId);
  console.log("From:", tx?.from);
  console.log("To (contract):", tx?.to);
  console.log("Block:", receipt.blockNumber, "Status:", receipt.status);

  // Try to decode the input method
  try {
    const decoded = iface.parseTransaction({ data: tx.data, value: tx.value });
    console.log("Method:", decoded?.name);
    if (decoded?.name === "transferWithAuthorization") {
      const { from, to, value, validAfter, validBefore, nonce } = decoded.args;
      console.log("transferWithAuthorization args:", {
        from,
        to,
        value: value.toString(),
        validAfter: validAfter.toString(),
        validBefore: validBefore.toString(),
        nonce,
      });
    }
  } catch (_e) {
    // Not decodable with known ABI
  }

  const wantedToken = process.env.ASSET_ADDRESS?.toLowerCase();
  const logs = receipt.logs || [];
  if (logs.length === 0) {
    // Fallback: query logs directly from the provider for this block and contract
    const filter = {
      address: tx?.to,
      fromBlock: receipt.blockNumber,
      toBlock: receipt.blockNumber,
    };
    const fetched = await provider.getLogs(filter);
    if (!fetched || fetched.length === 0) {
      console.log("No logs found on receipt or by provider.getLogs().");
      return;
    }
    console.log("Decoded logs (fetched):");
    for (const log of fetched) {
      if (wantedToken && log.address.toLowerCase() !== wantedToken) continue;
      let parsed;
      try {
        parsed = iface.parseLog({ topics: log.topics, data: log.data });
      } catch (_e) {}
      if (parsed) {
        const out = { event: parsed.name, token: log.address };
        if (parsed.name === "Transfer") {
          const { from, to, value } = parsed.args;
          console.log({ ...out, from, to, value: value.toString() });
        } else if (parsed.name === "Approval") {
          const { owner, spender, value } = parsed.args;
          console.log({ ...out, owner, spender, value: value.toString() });
        } else if (parsed.name === "AuthorizationUsed" || parsed.name === "AuthorizationCanceled") {
          const { authorizer, nonce } = parsed.args;
          console.log({ ...out, authorizer, nonce });
        } else {
          console.log(out);
        }
      } else {
        console.log({ token: log.address, topic0: log.topics?.[0] });
      }
    }
    return;
  }

  console.log("Decoded logs:");
  for (const log of logs) {
    if (wantedToken && log.address.toLowerCase() !== wantedToken) continue;
    let parsed;
    try {
      parsed = iface.parseLog({ topics: log.topics, data: log.data });
    } catch (_e) {}
    if (parsed) {
      const out = { event: parsed.name, token: log.address };
      if (parsed.name === "Transfer") {
        const { from, to, value } = parsed.args;
        console.log({ ...out, from, to, value: value.toString() });
      } else if (parsed.name === "Approval") {
        const { owner, spender, value } = parsed.args;
        console.log({ ...out, owner, spender, value: value.toString() });
      } else if (parsed.name === "AuthorizationUsed" || parsed.name === "AuthorizationCanceled") {
        const { authorizer, nonce } = parsed.args;
        console.log({ ...out, authorizer, nonce });
      } else {
        console.log(out);
      }
    } else {
      console.log({ token: log.address, topic0: log.topics?.[0] });
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});


