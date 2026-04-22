from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.db.models import PaymentStatus


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: Literal["RUB", "USD", "EUR"]
    description: str = Field(min_length=1, max_length=1000)
    metadata: dict = Field(default_factory=dict)
    webhook_url: HttpUrl


class PaymentResponse(BaseModel):
    payment_id: UUID
    amount: Decimal
    currency: str
    description: str
    metadata: dict
    status: PaymentStatus
    webhook_url: HttpUrl
    idempotency_key: str
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PaymentAccepted(BaseModel):
    payment_id: UUID
    status: PaymentStatus
    created_at: datetime
