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
from inspect import Parameter, signature

from x402_a2a.core.helpers import paid_service, require_payment, smart_paid_service


class _Message:
    def __init__(self, metadata):
        self.metadata = metadata


class _Status:
    def __init__(self, metadata):
        self.message = _Message(metadata)


class _Task:
    def __init__(self, metadata):
        self.status = _Status(metadata)


class _Context:
    def __init__(self, payment_status):
        self.current_task = _Task({"x402.payment.status": payment_status})


def test_payment_helpers_require_resource_in_signature():
    for helper in [require_payment, paid_service, smart_paid_service]:
        resource = signature(helper).parameters["resource"]
        assert resource.default is Parameter.empty
        assert resource.annotation is str


def test_require_payment_requires_explicit_resource():
    with pytest.raises(TypeError, match="resource"):
        require_payment(
            price="$1.00",
            pay_to_address="0x0000000000000000000000000000000000000001",
        )


def test_require_payment_rejects_blank_resource():
    with pytest.raises(ValueError, match="resource"):
        require_payment(
            price="$1.00",
            pay_to_address="0x0000000000000000000000000000000000000001",
            resource="",
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


def test_paid_service_requires_explicit_resource_in_signature():
    with pytest.raises(TypeError, match="resource"):
        paid_service(
            price="$1.00",
            pay_to_address="0x0000000000000000000000000000000000000001",
        )


def test_paid_service_rejects_blank_resource_at_decoration_time():
    with pytest.raises(ValueError, match="resource"):
        paid_service(
            price="$1.00",
            pay_to_address="0x0000000000000000000000000000000000000001",
            resource="",
        )(lambda: "ok")


def test_smart_paid_service_requires_explicit_resource_in_signature():
    with pytest.raises(TypeError, match="resource"):
        smart_paid_service(
            price="$1.00",
            pay_to_address="0x0000000000000000000000000000000000000001",
        )


def test_smart_paid_service_rejects_blank_resource_at_decoration_time():
    with pytest.raises(ValueError, match="resource"):
        smart_paid_service(
            price="$1.00",
            pay_to_address="0x0000000000000000000000000000000000000001",
            resource="",
        )(lambda: "ok")


def test_smart_paid_service_detects_paid_keyword_context():
    @smart_paid_service(
        price="$1.00",
        pay_to_address="0x0000000000000000000000000000000000000001",
        resource="https://api.example.com/service",
    )
    def service(*, context):
        return "ok"

    context = _Context("payment-completed")

    assert service(context=context) == "ok"
