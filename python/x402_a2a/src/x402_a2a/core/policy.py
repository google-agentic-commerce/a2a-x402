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
"""Spending policy hooks for x402ServerExecutor.

Addresses the security gaps identified in
https://github.com/google-agentic-commerce/a2a-x402/issues/60 — specifically
per-agent spending limits and circuit breakers. The default executor wires a
`NoOpSpendingPolicy` so behavior is unchanged unless a policy is supplied.

Two abstractions:

  * `SpendingPolicy` — abstract base. Implement `check` to reject a payment
    before settlement, and `record_settlement` to update internal state from
    the settlement outcome.
  * `BoundedSpendPolicy` — reference in-memory implementation with per-tx,
    hourly, and daily caps plus a consecutive-failure circuit breaker.

`BoundedSpendPolicy` is intentionally simple: a sliding window of timestamps
keyed by `pay_to`, suitable for single-process agents. Production
deployments with multiple workers should subclass `SpendingPolicy` against
shared state (Redis, a DB, etc.) — the abstract base does not constrain
the backend.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

from ..types import PaymentPayload, PaymentRequirements


@dataclass
class PolicyDecision:
    """Outcome of a `SpendingPolicy.check`.

    `allowed=True` lets settlement proceed. `allowed=False` short-circuits
    payment with `reason` surfaced to the caller via `error_reason` on the
    failure response.
    """

    allowed: bool
    reason: Optional[str] = None

    @classmethod
    def allow(cls) -> "PolicyDecision":
        return cls(allowed=True)

    @classmethod
    def deny(cls, reason: str) -> "PolicyDecision":
        return cls(allowed=False, reason=reason)


class SpendingPolicy(ABC):
    """Pre-settlement policy hook.

    The executor calls `check` after payment payload + requirements are
    resolved but before `verify_payment` / `settle_payment`. A denied
    decision aborts the flow without touching the facilitator. After a
    settlement attempt completes, `record_settlement` is invoked with the
    outcome so stateful policies (rate limits, circuit breakers) can update.
    """

    @abstractmethod
    def check(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
    ) -> PolicyDecision:
        """Return `PolicyDecision.allow()` to proceed, or `deny(...)` to abort."""

    @abstractmethod
    def record_settlement(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
        success: bool,
    ) -> None:
        """Record the outcome of a settlement attempt for stateful policies."""


class NoOpSpendingPolicy(SpendingPolicy):
    """Default policy: allow every payment, record nothing.

    Wired automatically when no policy is supplied so existing executors
    are behavior-preserving.
    """

    def check(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
    ) -> PolicyDecision:
        return PolicyDecision.allow()

    def record_settlement(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
        success: bool,
    ) -> None:
        return None


def _amount_int(requirements: PaymentRequirements) -> int:
    """Best-effort integer parse of a `max_amount_required` string."""
    raw = requirements.max_amount_required
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


@dataclass
class _RecipientWindow:
    """Per-`pay_to` sliding-window state used by `BoundedSpendPolicy`."""

    settled: Deque[tuple[float, int]] = field(default_factory=deque)
    consecutive_failures: int = 0
    circuit_open_until: float = 0.0


class BoundedSpendPolicy(SpendingPolicy):
    """In-memory spending caps + consecutive-failure circuit breaker.

    Caps are applied per recipient (`PaymentRequirements.pay_to`) and are
    expressed in the smallest unit of the asset (matching the on-wire
    `max_amount_required` representation). Pass `None` for any cap to
    disable that bound.

    Args:
        per_tx_max: Maximum amount allowed in a single payment. Denied at
            `check`; the settlement is never attempted.
        hourly_max: Sum of amounts settled in the last 3600s. Includes
            the current payment when checking.
        daily_max: Sum of amounts settled in the last 86400s. Includes
            the current payment when checking.
        circuit_failure_threshold: Open the breaker after this many
            consecutive failed settlements per recipient.
        circuit_cooldown_seconds: How long the breaker stays open before
            allowing another attempt.
        clock: Override for testing. Defaults to `time.time`.
    """

    def __init__(
        self,
        per_tx_max: Optional[int] = None,
        hourly_max: Optional[int] = None,
        daily_max: Optional[int] = None,
        circuit_failure_threshold: int = 5,
        circuit_cooldown_seconds: float = 60.0,
        clock=time.time,
    ):
        self.per_tx_max = per_tx_max
        self.hourly_max = hourly_max
        self.daily_max = daily_max
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_cooldown_seconds = circuit_cooldown_seconds
        self._clock = clock
        self._state: Dict[str, _RecipientWindow] = defaultdict(_RecipientWindow)

    def _window(self, key: str) -> _RecipientWindow:
        return self._state[key]

    def _prune(self, window: _RecipientWindow, now: float, horizon: float) -> None:
        while window.settled and (now - window.settled[0][0]) > horizon:
            window.settled.popleft()

    def _sum_within(self, window: _RecipientWindow, now: float, horizon: float) -> int:
        total = 0
        for ts, amount in window.settled:
            if (now - ts) <= horizon:
                total += amount
        return total

    def check(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
    ) -> PolicyDecision:
        amount = _amount_int(requirements)
        recipient = requirements.pay_to or "<unknown>"
        now = self._clock()
        window = self._window(recipient)

        if window.circuit_open_until and now < window.circuit_open_until:
            return PolicyDecision.deny(
                f"circuit breaker open for {recipient} "
                f"(retry after {window.circuit_open_until - now:.1f}s)"
            )

        if self.per_tx_max is not None and amount > self.per_tx_max:
            return PolicyDecision.deny(
                f"per-tx cap exceeded: {amount} > {self.per_tx_max}"
            )

        if self.hourly_max is not None:
            self._prune(window, now, 86400.0)
            spent_hour = self._sum_within(window, now, 3600.0)
            if (spent_hour + amount) > self.hourly_max:
                return PolicyDecision.deny(
                    f"hourly cap exceeded: {spent_hour + amount} > {self.hourly_max}"
                )

        if self.daily_max is not None:
            self._prune(window, now, 86400.0)
            spent_day = self._sum_within(window, now, 86400.0)
            if (spent_day + amount) > self.daily_max:
                return PolicyDecision.deny(
                    f"daily cap exceeded: {spent_day + amount} > {self.daily_max}"
                )

        return PolicyDecision.allow()

    def record_settlement(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
        success: bool,
    ) -> None:
        recipient = requirements.pay_to or "<unknown>"
        amount = _amount_int(requirements)
        now = self._clock()
        window = self._window(recipient)

        if success:
            window.settled.append((now, amount))
            window.consecutive_failures = 0
            window.circuit_open_until = 0.0
        else:
            window.consecutive_failures += 1
            if window.consecutive_failures >= self.circuit_failure_threshold:
                window.circuit_open_until = now + self.circuit_cooldown_seconds
