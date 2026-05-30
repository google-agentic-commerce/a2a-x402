# Pre-spend MAKO verification in an A2A x402 flow

This example shows how a buyer agent in an A2A (Agent-to-Agent) conversation can pre-verify a target service before spending USDC against it, by calling MAKO's Verifier endpoint.

The flow:

1. Buyer agent receives an A2A request with a `paymentRequired` action targeting `https://target.example/api/foo`.
2. Before signing, buyer calls MAKO's `/api/agent-commerce/verify` ($0.25 USDC).
3. MAKO inspects the target's `/.well-known/x402.json`, validates schemas, checks settlement readiness, and returns a verdict + recommended call plan + signed receipt.
4. If the verdict is `callable` and score ≥ 70, buyer proceeds with the original A2A payment.
5. If not, buyer responds in the A2A conversation with the MAKO warnings instead of paying.

Total cost: $0.25 + the original target call. The verification receipt is hash-anchored so the buyer can persist it as proof-of-due-diligence in case of dispute.

## Run it

```bash
npm install
AGENT_PRIVATE_KEY=0x... TARGET_URL=https://some-x402-service npx tsx agent.ts
```

## Composability

For high-volume buyers, the Verifier is overkill on every call. The cheap pattern is to pre-screen with MAKO Pulse ($0.02) and only escalate to the Verifier when Pulse signals trouble. See the [MAKO architecture docs](https://github.com/ChrisDover/mako-verifier/blob/main/ARCHITECTURE.md#how-a-buyer-agent-composes-the-pillars) for that pattern and others.
