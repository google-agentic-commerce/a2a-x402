# Settle A2A x402 payments through Interline (non-custodial, no facilitator to run)

> Implement a2a-x402's `x402ServerExecutor` with [Interline](https://github.com/Choppaaahh/interline-routes)
> as the verify/settle backend, so your A2A merchant agent **runs no facilitator and holds no keys.**

a2a-x402 ships `x402ServerExecutor` as an **abstract base** — it drives the A2A x402
protocol but leaves two methods for you:

```python
async def verify_payment(self, payload, requirements) -> VerifyResponse: ...
async def settle_payment(self, payload, requirements) -> SettleResponse: ...
```

…because *who checks the signature and moves the funds* is a deployment choice. This
example points them at **Interline**, a neutral, non-custodial cross-rail x402 router.
The result:

- **No facilitator to operate, no keys to hold.** Interline verifies + settles; funds
  move buyer → your wallet directly. Interline never custodies.
- **Rail-agnostic settlement.** Today the same code settles **Base/EVM** x402. When
  a2a-x402 bumps its `x402` pin to a Solana-capable release, the *same* executor settles
  **Solana** too — no merchant change.

## How it composes (and why it's HTTP, not an import)

a2a-x402 pins `x402==0.3.x` (`x402.types`); Interline's router runs on `x402>=2`
(`x402.http`). They can't share one Python process — and they were never meant to.
Interline is a **facilitator service**, addressed over the **x402 wire protocol**
(`POST /verify`, `POST /settle`, JSON bodies) which is stable across `x402` library
versions. So `InterlineExecutor` is a thin *client*: it serializes the x402 objects to
the wire shape, hands them to Interline's endpoint, and maps the response back. Zero
shared dependency, zero version conflict.

```
A2A buyer agent ──pays──▶ your merchant agent
                          └─ InterlineExecutor(x402ServerExecutor)
                               verify_payment / settle_payment
                                     │  x402 wire protocol (HTTP/JSON)
                                     ▼
                          Interline facilitator (neutral, non-custodial)
                               └─ settles on the right rail → your wallet
```

## Files

| File | What |
|---|---|
| `interline_executor.py` | `InterlineExecutor(x402ServerExecutor)` + `interline_facilitator(base_url)` HTTP client |
| `selftest.py` | mock-verifies verify/settle mapping — **zero network, no A2A runtime** |

## Install (the versions a2a-x402 pins — not pip-latest)

```bash
pip install "git+https://github.com/google-agentic-commerce/a2a-x402#subdirectory=python/x402_a2a" \
            "a2a-sdk==0.3.1" "x402==0.3.0"
```

## Verify it works (no wallet, no chain, no Interline server)

```bash
python selftest.py
# -> SELFTEST PASS   (happy path + rejected-payment + network fall-through)
```

The selftest injects stub facilitator responses and asserts the x402 `VerifyResponse` /
`SettleResponse` come back correctly mapped — so it proves the integration logic without
standing up an agent runtime or a payment server.

## Use it for real

```python
from interline_executor import InterlineExecutor, interline_facilitator

verify_fn, settle_fn = interline_facilitator("https://your-interline-endpoint")  # needs httpx
executor = InterlineExecutor(your_agent_executor, x402_config,
                             verify_fn=verify_fn, settle_fn=settle_fn)
# register `executor` with your A2A server exactly like any x402ServerExecutor.
```

Point `interline_facilitator(...)` at your Interline deployment. Your wallet address
lives in the `PaymentRequirements` you advertise; Interline settles to it directly and
never holds funds.

## Notes

- Non-custodial end-to-end — neither a2a-x402 nor Interline custodies funds.
- The `verify_fn` / `settle_fn` seam is injectable, so swapping Interline for any other
  x402 facilitator (or a test stub) is a one-line change — the executor doesn't care.
- Happy to adjust framing/path or trim — just say the word.
