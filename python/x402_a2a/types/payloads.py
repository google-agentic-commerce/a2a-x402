"""Scheme-specific payload models for x402 exact payments."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SparkPaymentType(str, Enum):
    """Enumerates transports supported by the Spark exact scheme."""

    SPARK = "SPARK"
    LIGHTNING = "LIGHTNING"
    L1 = "L1"


class ExactSparkPaymentPayload(BaseModel):
    """Payload carried in the exact scheme when network == spark.

    The JSON representation maps to the `X-PAYMENT` header body described in
    `schemes/scheme_exact_spark.md` and mirrors its required/optional fields.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )

    payment_type: SparkPaymentType = Field(alias="paymentType")
    transfer_id: Optional[str] = Field(default=None, alias="transfer_id")
    preimage: Optional[str] = None
    txid: Optional[str] = None

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "ExactSparkPaymentPayload":
        """Enforce transport-specific requirements from the scheme specification."""

        if self.payment_type is SparkPaymentType.SPARK and not self.transfer_id:
            raise ValueError("transfer_id is required when paymentType is SPARK")
        if self.payment_type is SparkPaymentType.LIGHTNING and not self.preimage:
            raise ValueError("preimage is required when paymentType is LIGHTNING")
        if self.payment_type is SparkPaymentType.L1 and not self.txid:
            raise ValueError("txid is required when paymentType is L1")
        return self
