"""Mock-verify InterlineExecutor with ZERO network and no A2A agent runtime.

`verify_payment` / `settle_payment` are standalone async methods, so we can exercise
the whole Interline-routing seam by injecting stub facilitator functions and asserting
the x402 response objects come back correctly mapped. Golden fixtures (expected values
computed here, by hand) — the executor must reproduce them exactly.

    python selftest.py        # -> "SELFTEST PASS" + exit 0, or AssertionError + exit 1

Requires the a2a-x402 deps installed at the versions a2a-x402 pins:
    pip install "git+https://github.com/google-agentic-commerce/a2a-x402#subdirectory=python/x402_a2a" \
                "a2a-sdk==0.3.1" "x402==0.3.0"
"""
from __future__ import annotations

import asyncio
import sys

from a2a.server.agent_execution import AgentExecutor
from x402.types import ExactPaymentPayload, PaymentPayload, PaymentRequirements
from x402_a2a.types.config import x402ExtensionConfig

from interline_executor import InterlineExecutor

# --- golden fixtures (the merchant's EVM offer + a buyer's signed payment) ----------
BUYER = "0xBuyer0000000000000000000000000000000001"
MERCHANT = "0x000000000000000000000000000000000000dEaD"
TX = "0xSETTLEMENTtxhash0000000000000000000000000000000000000000000000000001"

REQUIREMENTS = PaymentRequirements(
    scheme="exact",
    network="base-sepolia",          # EVM — the only thing a2a-x402's pinned x402 0.3.0 allows
    max_amount_required="100000",    # 0.10 USDC (6 decimals)
    resource="https://merchant.example/premium-report",
    description="Premium report",
    mime_type="application/json",
    pay_to=MERCHANT,
    max_timeout_seconds=120,
    asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia test USDC
    extra={"name": "USDC", "version": "2"},
)

PAYLOAD = PaymentPayload(
    x402_version=1,
    scheme="exact",
    network="base-sepolia",
    payload=ExactPaymentPayload(
        signature="0x" + "ab" * 65,
        authorization={
            "from": BUYER,
            "to": MERCHANT,
            "value": "100000",
            "validAfter": "0",
            "validBefore": "9999999999",
            "nonce": "0x" + "00" * 32,
        },
    ),
)


# --- stubs: a no-op A2A delegate + Interline facilitator responses ------------------
class _StubAgent(AgentExecutor):
    async def execute(self, context, event_queue):  # pragma: no cover - never called here
        ...

    async def cancel(self, context, event_queue):  # pragma: no cover
        ...


CONFIG = x402ExtensionConfig()  # defaults are fine for the verify/settle unit path


def _make_executor(verify_raw: dict, settle_raw: dict) -> InterlineExecutor:
    return InterlineExecutor(
        _StubAgent(),
        CONFIG,
        verify_fn=lambda payment, requirements: verify_raw,
        settle_fn=lambda payment, requirements: settle_raw,
    )


def main() -> int:
    # 1) happy path — Interline verifies + settles, executor maps it to x402 responses
    ex = _make_executor(
        verify_raw={"is_valid": True, "payer": BUYER},
        settle_raw={"success": True, "transaction": TX, "network": "base-sepolia", "payer": BUYER},
    )
    vr = asyncio.run(ex.verify_payment(PAYLOAD, REQUIREMENTS))
    assert vr.is_valid is True, vr
    assert vr.invalid_reason is None, vr
    assert vr.payer == BUYER, vr

    sr = asyncio.run(ex.settle_payment(PAYLOAD, REQUIREMENTS))
    assert sr.success is True, sr
    assert sr.transaction == TX, sr
    assert sr.network == "base-sepolia", sr
    assert sr.payer == BUYER, sr
    print("  [1] happy path: verify is_valid=True, settle tx mapped, payer carried  OK")

    # 2) failure path — a rejected verify must surface is_valid=False + a reason
    ex2 = _make_executor(
        verify_raw={"is_valid": False, "reason": "invalid_signature"},
        settle_raw={"success": False, "reason": "not_settled"},
    )
    vr2 = asyncio.run(ex2.verify_payment(PAYLOAD, REQUIREMENTS))
    assert vr2.is_valid is False, vr2
    assert vr2.invalid_reason, vr2  # must carry a non-empty reason
    sr2 = asyncio.run(ex2.settle_payment(PAYLOAD, REQUIREMENTS))
    assert sr2.success is False, sr2
    assert sr2.error_reason, sr2
    print("  [2] failure path: verify is_valid=False+reason, settle success=False+reason  OK")

    # 3) network fall-through — if Interline omits network, executor uses the requirement's
    ex3 = _make_executor(
        verify_raw={"is_valid": True},
        settle_raw={"success": True, "transaction": TX},  # no network key
    )
    sr3 = asyncio.run(ex3.settle_payment(PAYLOAD, REQUIREMENTS))
    assert sr3.network == "base-sepolia", sr3  # fell through to requirements.network
    # payer fell through to the signed authorization's `from`
    assert sr3.payer == BUYER, sr3
    print("  [3] fall-through: missing network->requirements.network, payer<-authorization  OK")

    print("SELFTEST PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
