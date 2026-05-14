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
import pytest

from x402_a2a.core.helpers import paid_service, require_payment, smart_paid_service


def test_require_payment_requires_explicit_resource():
    with pytest.raises(ValueError, match="resource"):
        require_payment(
            price="$1.00",
            pay_to_address="0x0000000000000000000000000000000000000001",
        )


def test_require_payment_uses_explicit_resource():
    exception = require_payment(
        price="$1.00",
        pay_to_address="0x0000000000000000000000000000000000000001",
        resource="https://api.example.com/service",
    )

    assert (
        exception.get_accepts_array()[0].resource == "https://api.example.com/service"
    )


def test_paid_service_requires_explicit_resource():
    decorated = paid_service(
        price="$1.00",
        pay_to_address="0x0000000000000000000000000000000000000001",
    )(lambda: "ok")

    with pytest.raises(ValueError, match="resource"):
        decorated()


def test_smart_paid_service_requires_explicit_resource():
    decorated = smart_paid_service(
        price="$1.00",
        pay_to_address="0x0000000000000000000000000000000000000001",
    )(lambda: "ok")

    with pytest.raises(ValueError, match="resource"):
        decorated()
