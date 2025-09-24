"""Tests for the Cashu partner helpers."""

import pytest
from unittest.mock import MagicMock

from x402_a2a.partners.cashu import (
    create_cashu_payment_requirements,
    process_cashu_payment,
)
from x402_a2a.core.wallet import process_payment_required
from x402_a2a.types import (
    CashuPaymentPayload,
    PaymentRequirements,
    x402PaymentRequiredResponse,
)


def _build_cashu_requirement(**overrides) -> PaymentRequirements:
    base_kwargs = {
        "price": 1000,
        "pay_to_address": "cashu:merchant",
        "resource": "/cashu",
        "network": "bitcoin-testnet",
        "mint_urls": ["https://nofees.testnut.cashu.space/"],
    }
    base_kwargs.update(overrides)
    return create_cashu_payment_requirements(**base_kwargs)


def test_create_cashu_payment_requirements():
    requirements = create_cashu_payment_requirements(
        price=6000,
        pay_to_address="cashu:merchant",
        resource="/cashu",
        network="bitcoin-testnet",
        mint_urls=["https://nofees.testnut.cashu.space/"],
        keyset_id="keyset-1",
    )

    assert requirements.scheme == "cashu-token"
    assert requirements.max_amount_required == "6000"
    assert requirements.extra["mints"] == ["https://nofees.testnut.cashu.space/"]
    assert requirements.extra["keysetIds"] == ["keyset-1"]


def test_create_cashu_payment_requirements_missing_mint():
    with pytest.raises(ValueError) as exc:
        create_cashu_payment_requirements(
            price=1000,
            pay_to_address="cashu:merchant",
            resource="/cashu",
            network="bitcoin-regtest",
        )

    assert "network 'bitcoin-regtest'" in str(exc.value)


def test_create_cashu_payment_requirements_fractional_price():
    with pytest.raises(ValueError) as exc:
        create_cashu_payment_requirements(
            price=0.5,
            pay_to_address="cashu:merchant",
            resource="/cashu",
            network="bitcoin-testnet",
        )

    assert "whole number" in str(exc.value)


def test_create_cashu_payment_requirements_invalid_string_price():
    with pytest.raises(ValueError):
        create_cashu_payment_requirements(
            price="12.3",
            pay_to_address="cashu:merchant",
            resource="/cashu",
            network="bitcoin-testnet",
        )


def test_process_cashu_payment():
    requirements = _build_cashu_requirement(price="5000")

    payload = CashuPaymentPayload(
        tokens=[
            {
                "mint": "https://nofees.testnut.cashu.space/",
                "proofs": [
                    {
                        "amount": 5000,
                        "secret": "secret",
                        "C": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                        "id": "001122aabbccdd",
                    }
                ],
            }
        ],
        encoded=["cashuBexample"],
        payer="payer-id",
    )

    result = process_cashu_payment(requirements=requirements, cashu_payload=payload)

    assert result.scheme == "cashu-token"
    assert result.payload.tokens[0].mint == "https://nofees.testnut.cashu.space/"


def test_process_cashu_payment_requires_payload():
    requirements = _build_cashu_requirement()

    with pytest.raises(ValueError):
        process_cashu_payment(requirements=requirements, cashu_payload=None)


def test_process_cashu_payment_mismatched_mints():
    requirements = _build_cashu_requirement()

    payload = CashuPaymentPayload(
        tokens=[
            {
                "mint": "https://mint.minibits.cash/Bitcoin",
                "proofs": [
                    {
                        "amount": 1000,
                        "secret": "secret",
                        "C": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                        "id": "001122aabbccdd",
                    }
                ],
            }
        ],
        encoded=["cashuBexample"],
    )

    with pytest.raises(ValueError) as exc:
        process_cashu_payment(requirements=requirements, cashu_payload=payload)

    assert "mint.minibits.cash" in str(exc.value)


def test_process_cashu_payment_encoded_length_mismatch():
    requirements = _build_cashu_requirement()

    valid_payload = CashuPaymentPayload(
        tokens=[
            {
                "mint": "https://nofees.testnut.cashu.space/",
                "proofs": [
                    {
                        "amount": 1000,
                        "secret": "secret",
                        "C": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                        "id": "001122aabbccdd",
                    }
                ],
            }
        ],
        encoded=["cashuBexample"],
    )
    payload = CashuPaymentPayload.model_construct(
        tokens=valid_payload.tokens,
        encoded=[],
        memo=valid_payload.memo,
        unit=valid_payload.unit,
        locks=valid_payload.locks,
        payer=valid_payload.payer,
        expiry=valid_payload.expiry,
    )

    with pytest.raises(ValueError):
        process_cashu_payment(requirements=requirements, cashu_payload=payload)


def test_process_payment_required_rejects_cashu(monkeypatch):
    cashu_requirement = _build_cashu_requirement()

    class DummyClient:
        def __init__(self, *_, **__):
            pass

        def select_payment_requirements(self, accepts):
            return accepts[0]

    monkeypatch.setattr("x402_a2a.core.wallet.x402Client", DummyClient)

    payment_required = x402PaymentRequiredResponse(
        x402_version=1,
        accepts=[cashu_requirement],
        error="",
    )

    with pytest.raises(ValueError) as exc:
        process_payment_required(payment_required, account=MagicMock())

    assert "partners.cashu" in str(exc.value)
