from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .networks import SupportedNetworks
from .schemes import SupportedSchemes

class PaymentRequirements(BaseModel):
    plan_id: str
    agent_id: str
    max_amount: str
    network: SupportedNetworks
    scheme: SupportedSchemes
    extra: Optional[dict[str, Any]] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

    @field_validator("max_amount")
    def validate_max_amount(cls, v):
        try:
            int(v)
        except ValueError:
            raise ValueError(
                "max_amount must be an integer encoded as a string"
            )
        return v

class NvmPaymentRequiredResponse(BaseModel):
    nvm_version: int
    accepts: list[PaymentRequirements]
    error: str

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

class SessionKeyPayload(BaseModel):
    session_key: str

class PaymentPayload(BaseModel):
    nvm_version: int
    scheme: str
    network: str
    payload: SessionKeyPayload

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

class VerifyResponse(BaseModel):
    is_valid: bool = Field(alias="isValid")
    invalid_reason: Optional[str] = Field(None, alias="invalidReason")
    session_key: Optional[str] = Field(None, alias="sessionKey")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class SettleResponse(BaseModel):
    success: bool
    error_reason: Optional[str] = None
    transaction: Optional[str] = None
    network: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )