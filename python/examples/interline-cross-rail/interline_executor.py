"""InterlineExecutor — settle an A2A merchant's x402 payments through Interline,
non-custodially, without running your own facilitator.

a2a-x402 ships `x402ServerExecutor` as an ABSTRACT base: it drives the A2A payment
protocol (the `execute()` loop, the x402 extension handshake) but leaves two methods
for YOU to implement —

    async verify_payment(payload, requirements) -> VerifyResponse
    async settle_payment(payload, requirements) -> SettleResponse

— because *who actually checks the signature and moves the funds* is a deployment
choice. Most examples point those at a facilitator you host. This one points them at
[Interline](https://github.com/Choppaaahh/interline-routes), a **neutral, non-custodial
cross-rail x402 router**, so the merchant agent:

  * runs **no facilitator** and holds **no keys** (Interline verifies + settles; funds
    move buyer -> your wallet directly, Interline never custodies),
  * gets a **rail-agnostic** settlement path — today the same code settles Base/EVM
    x402; when a2a-x402 bumps its `x402` dependency to a Solana-capable version, the
    *same* executor settles Solana too, no merchant change.

## Why this talks to Interline over HTTP, not via import

a2a-x402 pins `x402==0.3.x` (module `x402.types`); Interline's router runs on
`x402>=2` (module `x402.http`). The two can't share one Python process. That's fine —
they were never meant to: Interline is a **facilitator service**, and a facilitator is
addressed over the **x402 wire protocol** (`POST /verify`, `POST /settle` with JSON
bodies), which is stable across `x402` library versions. So this executor is a thin
*client*: it serializes the x402 objects to the wire shape, hands them to Interline's
endpoint, and maps the response back. No shared dependency, no version conflict.

The `verify_fn` / `settle_fn` seam is injectable so the whole thing is unit-testable
with zero network (see selftest.py).
"""
from __future__ import annotations

from typing import Callable, Optional

from x402_a2a import x402ServerExecutor
from x402.types import (
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)

# A facilitator client is just: (payment_wire, requirements_wire) -> response_dict.
# Prod = an HTTP POST to Interline; tests inject a stub. Kept as a plain callable so
# the executor never imports Interline's (version-incompatible) Python package.
FacilitatorFn = Callable[[dict, dict], dict]


class InterlineExecutor(x402ServerExecutor):
    """An `x402ServerExecutor` whose verify/settle route to Interline.

    Parameters
    ----------
    delegate : AgentExecutor
        The A2A agent that does the actual paid work (handed straight to the base class).
    config : x402ExtensionConfig
        The x402 A2A extension config (handed straight to the base class).
    verify_fn, settle_fn : (payment: dict, requirements: dict) -> dict
        How payments are verified / settled. In production, build these with
        `interline_facilitator(base_url)` (HTTP to Interline). In tests, inject stubs.
    """

    def __init__(
        self,
        delegate,
        config,
        *,
        verify_fn: FacilitatorFn,
        settle_fn: FacilitatorFn,
    ) -> None:
        super().__init__(delegate, config)
        if not callable(verify_fn) or not callable(settle_fn):
            raise TypeError("verify_fn and settle_fn must be callables (payment, requirements) -> dict")
        self._verify_fn = verify_fn
        self._settle_fn = settle_fn

    async def verify_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """Validate the buyer's signed payment without moving funds — via Interline."""
        raw = self._verify_fn(_wire(payload), _wire(requirements))
        is_valid = bool(raw.get("is_valid", raw.get("isValid", False)))
        return VerifyResponse(
            is_valid=is_valid,
            # x402 expects an InvalidReason enum/string; only present when invalid.
            invalid_reason=None if is_valid else (raw.get("reason") or raw.get("invalid_reason") or "verification_failed"),
            payer=raw.get("payer") or _payer_of(payload),
        )

    async def settle_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """Move the funds (buyer -> merchant wallet) — via Interline, non-custodially."""
        raw = self._settle_fn(_wire(payload), _wire(requirements))
        success = bool(raw.get("success", False))
        return SettleResponse(
            success=success,
            error_reason=None if success else (raw.get("reason") or raw.get("error_reason")),
            # Interline returns the on-chain tx id under tx_hash/transaction; x402 calls it `transaction`.
            transaction=(raw.get("transaction") or raw.get("tx_hash") or ""),
            network=raw.get("network") or requirements.network,
            payer=raw.get("payer") or _payer_of(payload),
        )


def _wire(obj) -> dict:
    """Serialize an x402 pydantic object to its wire (camelCase) JSON shape."""
    return obj.model_dump(by_alias=True, exclude_none=True)


def _payer_of(payload: PaymentPayload) -> Optional[str]:
    """Best-effort buyer address from the signed authorization, for receipts."""
    try:
        inner = payload.payload  # ExactPaymentPayload
        auth = getattr(inner, "authorization", None) or {}
        if isinstance(auth, dict):
            return auth.get("from")
        return getattr(auth, "from_", None) or getattr(auth, "from", None)
    except (AttributeError, KeyError, TypeError):
        # best-effort only — a malformed payload shape just means "no payer label";
        # narrow exceptions so genuine bugs aren't swallowed (QA checklist item 3).
        return None


def interline_facilitator(base_url: str, *, timeout: float = 30.0) -> tuple[FacilitatorFn, FacilitatorFn]:
    """Build (verify_fn, settle_fn) that POST to a running Interline facilitator.

    Interline exposes the standard x402 facilitator endpoints; this is a thin client so
    the executor never imports Interline's (version-incompatible) package. Requires
    `httpx` at runtime (only when you use the real HTTP path — tests inject stubs and
    need nothing).

    PRODUCTION NOTE (this is an example — harden before real money): a transient 5xx on
    the *settle* call here raises and propagates, which can leave a payment "in flight"
    (buyer authorized, settlement unconfirmed). For real deployments, make `settle`
    **idempotent** (key it on the payment nonce so a retry can't double-settle) and wrap
    `_post` with bounded retries + a dead-letter path for the unrecoverable case. The
    seam is intentionally injectable so you can supply a hardened `settle_fn` without
    touching the executor.
    """
    import httpx  # local import: only needed for the live HTTP path

    base = base_url.rstrip("/")

    def _post(path: str, payment: dict, requirements: dict) -> dict:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(f"{base}{path}", json={"paymentPayload": payment, "paymentRequirements": requirements})
            r.raise_for_status()
            return r.json()

    return (
        lambda payment, requirements: _post("/verify", payment, requirements),
        lambda payment, requirements: _post("/settle", payment, requirements),
    )
