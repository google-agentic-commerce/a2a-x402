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
"""Replay protection for x402 payment authorizations (spec section 9)."""

import heapq
import time
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Tuple

# Keep expired entries briefly past their deadline so clock skew or sub-second
# boundary crossings cannot evict a nonce that just passed an expiry check.
_EXPIRY_GRACE_SECONDS = 60
_DEFAULT_MAX_ENTRIES = 100_000


class PaymentNonceStore(ABC):
    """Records payment authorization nonces that have already been accepted.

    Servers MUST track used nonces to prevent replay attacks. Deployments
    that run more than one server replica must use a shared implementation so
    that a payload accepted by one replica is rejected by all others.
    """

    @abstractmethod
    async def reserve(self, key: str, expires_at: int) -> bool:
        """Atomically marks a nonce as used.

        Args:
            key: Identifies the nonce (network, asset, payer and nonce).
            expires_at: Unix time at which the authorization stops being
                valid. The entry may be dropped once this time has passed.

        Returns:
            True if the nonce was unused and unexpired and is now reserved,
            or False if it was already reserved or expired.
        """
        raise NotImplementedError


class InMemoryPaymentNonceStore(PaymentNonceStore):
    """Process-local nonce store for single-replica servers and tests.

    Entries are kept until their authorization expires (plus a short grace
    window) and bounded by ``max_entries`` so clients signing far-future
    ``valid_before`` timestamps cannot grow memory without bound.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ):
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._clock = clock
        self._max_entries = max_entries
        self._expiry: Dict[str, int] = {}
        self._expiry_heap: List[Tuple[int, str]] = []

    async def reserve(self, key: str, expires_at: int) -> bool:
        now = self._clock()
        self._prune(now)
        if expires_at <= now:
            return False
        if key in self._expiry:
            return False
        if len(self._expiry) >= self._max_entries:
            oldest_key = next(iter(self._expiry))
            del self._expiry[oldest_key]
        self._expiry[key] = expires_at
        heapq.heappush(self._expiry_heap, (expires_at, key))
        return True

    def _prune(self, now: float) -> None:
        cutoff = now - _EXPIRY_GRACE_SECONDS
        while self._expiry_heap and self._expiry_heap[0][0] <= cutoff:
            exp, key = heapq.heappop(self._expiry_heap)
            if self._expiry.get(key) == exp:
                del self._expiry[key]
