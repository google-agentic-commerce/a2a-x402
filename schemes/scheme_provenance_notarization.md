# Post-Payment Provenance Scheme for A2A x402

## Overview

This document specifies an experimental scheme for **post-payment provenance** — a complementary layer to the x402 payment flow that enables a Merchant Agent to cryptographically prove the existence and integrity of its output after a paid A2A transaction.

The scheme uses an independent notary service (AOTrust) to issue a **Provenance Data Record (PDR)** — a 239-byte binary record signed with Ed25519 and anchored on-chain via NEAR Merkle anchoring. The PDR binds the output artifact hash to a timestamp and the x402 payment hash, creating a non-repudiable chain of custody.

This is **not** a payment scheme. It is a **provenance extension** that runs after payment settlement, adding cryptographic proof-of-existence to the A2A transaction output.

## Scheme Name

`provenance-notarization`

## Motivation

In the standard A2A x402 flow, payment proves **intent** — the client authorized payment for a service. But there is no cryptographic proof that:

1. The merchant agent produced a specific output at a specific time
2. The output was not retroactively modified
3. The output corresponds to the specific payment that funded it

This scheme adds a **post-transaction provenance layer**:

- **AP2** proves the client intended to pay
- **x402** proves the payment settled on-chain
- **Provenance notarization** proves the merchant's output existed at a point in time

## Relationship to Existing Schemes

This scheme is **complementary** to all existing `exact` payment schemes (Lightning, Spark, UMA, Base). It does not replace or modify the payment flow — it adds a step after payment settlement.

```
Existing x402 flow:
  Client → Merchant: Request service
  Merchant → Client: 402 Payment Required
  Client → Merchant: PaymentPayload (signed)
  Merchant: Verify + Settle payment
  Merchant → Client: Service result (Artifact)

Extended flow with provenance:
  Client → Merchant: Request service
  Merchant → Client: 402 Payment Required
  Client → Merchant: PaymentPayload (signed)
  Merchant: Verify + Settle payment
  Merchant: Build PDR (work_hash = SHA-256(output), payment_hash = tx_hash)
  Merchant → Notary: Notarize request + x402 payment
  Notary → Merchant: PDR (239 bytes, Ed25519 signed)
  Merchant → Client: Service result + PDR (in artifact metadata)
  Client: Verify PDR offline (self-contained signature)
  Notary: Batch PDRs → Merkle root → NEAR anchor (every ~16 min)
```

## Protocol Flow

### After Payment Settlement (Step 6 of A2A x402 v0.1)

Once the Merchant Agent has verified and settled the payment, and before returning the final `Task` with the service result:

1. **Merchant Agent** computes `work_hash = SHA-256(serialized_output_artifact)`
2. **Merchant Agent** sends a notarization request to an independent Notary Service (e.g., AOTrust at `https://api.aotrust.link/v1/notarize`)
3. **Notary Service** verifies the x402 payment on-chain (Base L2 — checks EIP-3009 `transferWithAuthorization` event, confirms amount and recipient)
4. **Notary Service** builds a PDR containing: `work_hash`, `payment_hash` (EVM tx hash), `timestamp`, `issuer_id` (notary NEAR account), `payment_anchor_type` (0x05 = X402_BASE)
5. **Notary Service** signs the PDR with Ed25519 (NEP-413 standard — raw buffer, no SHA-256 pre-hash)
6. **Notary Service** returns the PDR (239 bytes, base64-encoded) to the Merchant Agent
7. **Merchant Agent** includes the PDR in the `Artifact` metadata of the final `Task` response
8. **Client Agent** (or any third party) can verify the PDR offline using the notary's public key

### Periodic Anchoring (Notary Service)

The Notary Service batches PDRs into Merkle trees every ~16 minutes and anchors the root on NEAR mainnet via the `merkle_anchor` contract. This provides a second layer of timestamping independent of the notary's own clock.

## PDR Format (239 bytes, External)

The PDR is a binary record with a self-contained Ed25519 signature:

| Offset | Field | Size | Content |
|--------|-------|------|---------|
| 0 | version | 1 | 0x03 |
| 1 | sig_scheme | 1 | 0x01 (Ed25519) |
| 2 | payment_anchor_type | 1 | 0x05 (X402_BASE) |
| 3 | timestamp_utc | 8 | Unix seconds |
| 11 | issuer_id | 36 | Notary NEAR account (NUL-padded) |
| 47 | subject_hash | 32 | SHA-256 of merchant agent account |
| 79 | payload_hash | 32 | SHA-256 of work artifact |
| 111 | merkle_root | 32 | Merkle batch anchor (filled after anchoring) |
| 143 | payment_hash | 32 | EVM tx hash (Base L2) |
| 175 | signature | 64 | Ed25519 (NEP-413) |

The `payment_anchor_type` is inside the signed payload — the PDR self-proves how the service was paid for, without external metadata.

**Full specification:** [pdr-spec.md](https://github.com/GitSerge-crypto/aotrust-skills/blob/main/pdr-spec.md)
**Standalone parser:** [pdr_parser.py](https://github.com/GitSerge-crypto/aotrust-skills/blob/main/pdr_parser.py) (zero dependencies, MIT)

## A2A Message Extension

### Artifact Metadata

The Merchant Agent includes the PDR in the `Artifact` metadata:

```json
{
  "artifacts": [
    {
      "artifactId": "result-001",
      "name": "Agent Analysis Report",
      "parts": [
        {
          "type": "data",
          "content": {
            "report": "Q3 revenue projection: $2.4M..."
          }
        }
      ],
      "metadata": {
        "x402.provenance": {
          "pdr_b64": "AwFCAUJ...base64-encoded 239-byte PDR...",
          "notary_pubkey": "490f51f23b993eacaff54fc977d9a7689ab7d4ae91504dc6cbdeadb2dbf1f462",
          "notary_issuer": "notary-node.near",
          "verify_url": "https://api.aotrust.link/v1/pdr/verify/",
          "verify_page": "https://verify.aotrust.link"
        }
      }
    }
  ]
}
```

### Task State Extension

The `x402.payment.status` metadata field is extended with a `provenance-attached` state:

```json
{
  "x402.payment.status": "payment-complete",
  "x402.provenance.status": "provenance-attached"
}
```

## Verification

### Offline (No API calls)

The Client Agent can verify the PDR using only the notary's public key and the PDR bytes:

```python
from pdr_parser import parse_pdr, verify_pdr

pdr = parse_pdr(base64.b64decode(pdr_b64))
is_valid = verify_pdr(pdr, notary_pubkey="490f51f2...")
# is_valid = True → signature matches, PDR is authentic
```

### Online (Notary API)

```bash
curl -s "https://api.aotrust.link/v1/pdr/verify/<pdr_b64>"
# Returns: valid, timestamp, issuer, anchor TX, etc.
```

### On-chain (NEAR Explorer)

The `merkle_root` field in the PDR corresponds to a NEAR transaction. Verify at `nearblocks.io/address/tx/<near_anchor_tx>`.

## Security Considerations

**Notary Independence**: The notary service must be independent from the merchant agent. The notary signs with its own Ed25519 key, creating a non-repudiable proof that the notary (not the merchant) attests to the artifact's existence.

**Blind Notarization**: The notary receives only the `work_hash` (SHA-256), never the original artifact. This preserves the merchant's output confidentiality.

**Payment Binding**: The `payment_hash` in the PDR is the EVM transaction hash of the x402 USDC transfer. This cryptographically binds the provenance record to the specific payment, preventing reuse of a PDR for a different transaction.

**Signature Coverage**: The Ed25519 signature covers the `payment_anchor_type` field (0x05 = X402_BASE). This means the PDR self-proves the payment method — no external attestation needed.

**Double-Notarization Prevention**: The notary service enforces a unique constraint on `(payment_anchor_type, payment_ref)` — each payment hash can only produce one PDR.

**Anchor Immutability**: Once the Merkle root is anchored on NEAR, it cannot be modified. NEAR consensus provides the final timestamp layer.

## Use Cases

| Scenario | What PDR Proves |
|----------|----------------|
| AI agent produces a financial report | Report existed at time T, paid via x402, unmodified |
| Code review by autonomous agent | Review output timestamped and signed by independent notary |
| Multi-agent pipeline (A→B→C) | Each stage notarized → full chain of custody |
| Agent dispute resolution | "Did the agent produce X at time T?" → PDR answers |
| Compliance / regulatory | Independent cryptographic timestamp from third-party notary |

## Cost

- $0.01 USDC per PDR (10,000 micro-USDC on Base L2)
- No API keys required for x402 flow
- No subscription, no prepaid credits

## Live Status

- Mainnet live since June 9, 2026
- 9 PDRs issued on Base Mainnet, all anchored on NEAR (3 anchor transactions)
- Notary public key: `490f51f23b993eacaff54fc977d9a7689ab7d4ae91504dc6cbdeadb2dbf1f462`
- API: `https://api.aotrust.link`
- MCP: `https://api.aotrust.link/mcp`
- Verify: `https://verify.aotrust.link`
- PDR spec + parser: [github.com/GitSerge-crypto/aotrust-skills](https://github.com/GitSerge-crypto/aotrust-skills)

---

## References

- [A2A x402 Extension Specification v0.1](../spec/v0.1/spec.md)
- [x402 Protocol](https://github.com/coinbase/x402)
- [PDR v2.3 Binary Format Specification](https://github.com/GitSerge-crypto/aotrust-skills/blob/main/pdr-spec.md)
- [PDR Parser (standalone, MIT)](https://github.com/GitSerge-crypto/aotrust-skills/blob/main/pdr_parser.py)
- [AOTrust Documentation](https://docs.aotrust.link)
- [NEP-413 Signing Standard](https://github.com/near/NEPs/blob/master/neps/nep-0413.md)