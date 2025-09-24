# Cashu Partner Helpers

Use these helpers to integrate Cashu payments without extending the core `x402_a2a.core` modules.

## Creating payment requirements

```python
from x402_a2a.partners.cashu import create_cashu_payment_requirements

requirements = create_cashu_payment_requirements(
    price=1000,
    pay_to_address="cashu:merchant",
    resource="/cashu",
    network="bitcoin-testnet",
    mint_urls=["https://nofees.testnut.cashu.space/"],
    facilitator_url="https://facilitator.example",
    keyset_ids=["keyset-1"],
)
```

The helper enforces:
- An explicit or default mint for the chosen Bitcoin network
- Whole-number satoshi prices
- Optional partner metadata such as facilitator URLs, keysets, and NUT-10 locks

## Processing a Cashu payment

```python
from x402_a2a.partners.cashu import process_cashu_payment
from x402_a2a.core.wallet import process_payment_required

payload = ...  # `CashuPaymentPayload`
requirements = ...  # `PaymentRequirements`

payment_payload = process_cashu_payment(
    requirements=requirements,
    cashu_payload=payload,
)
```

Call `process_payment_required` only for non-Cashu schemes. For Cashu, use `process_cashu_payment` directly so you can supply the encoded proofs.
