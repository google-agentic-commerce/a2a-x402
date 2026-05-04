# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for the spending policy hook (issue #60)."""

import pytest

from x402_a2a.core.policy import (
    BoundedSpendPolicy,
    NoOpSpendingPolicy,
    PolicyDecision,
    SpendingPolicy,
)
from x402_a2a.types import PaymentPayload, PaymentRequirements, x402ErrorCode


def _requirements(amount: str = "100", pay_to: str = "0xabc") -> PaymentRequirements:
    return PaymentRequirements(
        scheme="exact",
        network="base-sepolia",
        pay_to=pay_to,
        max_amount_required=amount,
        asset="0x456",
        description="test",
        resource="/test",
        mime_type="application/json",
        max_timeout_seconds=600,
    )


def _payload() -> PaymentPayload:
    return PaymentPayload(
        x402_version=1,
        scheme="exact",
        network="base-sepolia",
        payload={
            "signature": "0xsig",
            "authorization": {
                "from": "0xpayer",
                "to": "0xabc",
                "value": "100",
                "valid_after": "0",
                "valid_before": "9999999999",
                "nonce": "0xnonce",
            },
        },
    )


class _FakeClock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_policy_decision_allow_and_deny():
    allow = PolicyDecision.allow()
    assert allow.allowed is True
    assert allow.reason is None

    deny = PolicyDecision.deny("nope")
    assert deny.allowed is False
    assert deny.reason == "nope"


def test_noop_policy_allows_everything_and_records_nothing():
    policy = NoOpSpendingPolicy()
    decision = policy.check(_payload(), _requirements("999999999"))
    assert decision.allowed is True
    assert isinstance(policy, SpendingPolicy)
    policy.record_settlement(_payload(), _requirements(), success=False)


def test_bounded_per_tx_cap_rejects_oversized_payment():
    policy = BoundedSpendPolicy(per_tx_max=500)
    decision = policy.check(_payload(), _requirements("501"))
    assert decision.allowed is False
    assert "per-tx cap exceeded" in (decision.reason or "")


def test_bounded_per_tx_cap_allows_at_cap():
    policy = BoundedSpendPolicy(per_tx_max=500)
    decision = policy.check(_payload(), _requirements("500"))
    assert decision.allowed is True


def test_bounded_hourly_cap_rejects_after_window_fills():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(hourly_max=1000, clock=clock)

    for _ in range(10):
        assert policy.check(_payload(), _requirements("100")).allowed is True
        policy.record_settlement(_payload(), _requirements("100"), success=True)

    decision = policy.check(_payload(), _requirements("1"))
    assert decision.allowed is False
    assert "hourly cap exceeded" in (decision.reason or "")


def test_bounded_hourly_cap_window_slides():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(hourly_max=1000, clock=clock)

    for _ in range(10):
        policy.record_settlement(_payload(), _requirements("100"), success=True)

    assert policy.check(_payload(), _requirements("1")).allowed is False

    clock.advance(3601.0)
    assert policy.check(_payload(), _requirements("100")).allowed is True


def test_bounded_daily_cap_independent_of_hourly():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(hourly_max=10_000, daily_max=1_000, clock=clock)

    policy.record_settlement(_payload(), _requirements("900"), success=True)
    decision = policy.check(_payload(), _requirements("200"))
    assert decision.allowed is False
    assert "daily cap exceeded" in (decision.reason or "")


def test_bounded_caps_are_per_recipient():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(hourly_max=500, clock=clock)

    for _ in range(5):
        policy.record_settlement(
            _payload(), _requirements("100", pay_to="0xrecipientA"), success=True
        )

    assert (
        policy.check(_payload(), _requirements("100", pay_to="0xrecipientA")).allowed
        is False
    )
    assert (
        policy.check(_payload(), _requirements("100", pay_to="0xrecipientB")).allowed
        is True
    )


def test_circuit_breaker_opens_after_threshold():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(
        circuit_failure_threshold=3,
        circuit_cooldown_seconds=30.0,
        clock=clock,
    )

    for _ in range(3):
        assert policy.check(_payload(), _requirements()).allowed is True
        policy.record_settlement(_payload(), _requirements(), success=False)

    decision = policy.check(_payload(), _requirements())
    assert decision.allowed is False
    assert "circuit breaker open" in (decision.reason or "")


def test_circuit_breaker_closes_after_cooldown():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(
        circuit_failure_threshold=2,
        circuit_cooldown_seconds=30.0,
        clock=clock,
    )

    for _ in range(2):
        policy.record_settlement(_payload(), _requirements(), success=False)

    assert policy.check(_payload(), _requirements()).allowed is False

    clock.advance(31.0)
    assert policy.check(_payload(), _requirements()).allowed is True


def test_circuit_breaker_resets_on_successful_settlement():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(
        circuit_failure_threshold=3,
        circuit_cooldown_seconds=30.0,
        clock=clock,
    )

    for _ in range(2):
        policy.record_settlement(_payload(), _requirements(), success=False)
    policy.record_settlement(_payload(), _requirements(), success=True)

    for _ in range(2):
        assert policy.check(_payload(), _requirements()).allowed is True
        policy.record_settlement(_payload(), _requirements(), success=False)

    assert policy.check(_payload(), _requirements()).allowed is True


def test_failed_settlement_does_not_consume_budget():
    clock = _FakeClock()
    policy = BoundedSpendPolicy(hourly_max=100, clock=clock)

    policy.record_settlement(_payload(), _requirements("100"), success=False)

    decision = policy.check(_payload(), _requirements("100"))
    assert decision.allowed is True


def test_disabled_caps_allow_everything():
    policy = BoundedSpendPolicy()
    huge = _requirements("999999999999999999999999")
    assert policy.check(_payload(), huge).allowed is True


def test_policy_rejected_error_code_registered():
    assert x402ErrorCode.POLICY_REJECTED == "POLICY_REJECTED"
    assert x402ErrorCode.POLICY_REJECTED in x402ErrorCode.get_all_codes()


def test_subclass_can_replace_storage_backend():
    class StatelessAllowAll(SpendingPolicy):
        def check(self, payload, requirements):
            return PolicyDecision.allow()

        def record_settlement(self, payload, requirements, success):
            return None

    p = StatelessAllowAll()
    assert p.check(_payload(), _requirements("9999999")).allowed is True


@pytest.mark.asyncio
async def test_executor_short_circuits_on_policy_denial():
    """End-to-end: a denying policy aborts before verify/settle are called."""
    from unittest.mock import AsyncMock, MagicMock

    from a2a.types import Message, Task, TaskState, TaskStatus, TextPart

    from x402_a2a.executors.server import x402ServerExecutor
    from x402_a2a.types import (
        PaymentStatus,
        SettleResponse,
        VerifyResponse,
        x402Metadata,
    )

    class _DenyAll(SpendingPolicy):
        def __init__(self):
            self.records = []

        def check(self, payload, requirements):
            return PolicyDecision.deny("budget exhausted")

        def record_settlement(self, payload, requirements, success):
            self.records.append(success)

    class _Concrete(x402ServerExecutor):
        async def verify_payment(self, payload, requirements):
            return VerifyResponse(is_valid=True, payer="0xpayer")

        async def settle_payment(self, payload, requirements):
            return SettleResponse(success=True)

    delegate = AsyncMock()
    policy = _DenyAll()
    executor = _Concrete(delegate=delegate, config=MagicMock(), policy=policy)
    executor.verify_payment = AsyncMock(
        return_value=VerifyResponse(is_valid=True, payer="0xpayer")
    )
    executor.settle_payment = AsyncMock(return_value=SettleResponse(success=True))

    context = MagicMock()
    context.task_id = "task-deny"
    context.context_id = "context-deny"
    event_queue = AsyncMock()

    payment_payload = _payload()
    context.message = Message(
        messageId="msg-1",
        role="user",
        parts=[TextPart(text="test")],
        metadata={
            x402Metadata.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
            x402Metadata.PAYLOAD_KEY: payment_payload.model_dump(by_alias=True),
        },
    )
    context.current_task = Task(
        id="task-deny",
        contextId="context-deny",
        status=TaskStatus(state=TaskState.working),
        metadata={},
    )

    executor._payment_requirements_store[context.current_task.id] = [_requirements()]

    await executor.execute(context, event_queue)

    executor.verify_payment.assert_not_called()
    executor.settle_payment.assert_not_called()
    delegate.execute.assert_not_called()
    assert event_queue.enqueue_event.await_count >= 1
    assert policy.records == []
