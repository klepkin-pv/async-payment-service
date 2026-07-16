from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Outbox, PaymentStatus
from app.schemas.payment import PaymentCreate
from app.services.payments import create_or_get_payment, get_payment, list_payments

pytestmark = pytest.mark.asyncio


def sample_payment_create(
    *, amount: Decimal | None = None, description: str = "Service test", **overrides: object
) -> PaymentCreate:
    return PaymentCreate(
        amount=amount or Decimal("250.00"),
        currency="USD",
        description=description,
        webhook_url="https://example.com/callback",
        **overrides,
    )


async def test_create_payment_stores_record_and_outbox(session: AsyncSession) -> None:
    payload = sample_payment_create()
    payment = await create_or_get_payment(session, payload, idempotency_key="svc-1")

    assert payment.id is not None
    assert payment.amount == Decimal("250.00")
    assert payment.currency == "USD"
    assert payment.status == PaymentStatus.pending
    assert payment.idempotency_key == "svc-1"

    outbox = await session.scalar(select(Outbox))
    assert outbox is not None
    assert outbox.topic == "payments.new"
    assert outbox.payload["payment_id"] == str(payment.id)
    assert outbox.payload["idempotency_key"] == "svc-1"


async def test_create_payment_is_idempotent_by_key(session: AsyncSession) -> None:
    payload = sample_payment_create()
    first = await create_or_get_payment(session, payload, idempotency_key="svc-2")

    second_payload = sample_payment_create(amount=Decimal("999.00"))
    second = await create_or_get_payment(session, second_payload, idempotency_key="svc-2")

    assert first.id == second.id
    assert second.amount == Decimal("250.00")


async def test_get_payment_returns_none_when_missing(session: AsyncSession) -> None:
    from uuid import uuid4

    result = await get_payment(session, uuid4())
    assert result is None


async def test_list_payments_orders_by_created_at_desc(session: AsyncSession) -> None:
    for index in range(3):
        await create_or_get_payment(
            session,
            sample_payment_create(description=f"#{index}"),
            idempotency_key=f"list-svc-{index}",
        )

    payments = await list_payments(session, limit=10, offset=0)
    assert len(payments) == 3
    assert payments[0].idempotency_key == "list-svc-2"
    assert payments[2].idempotency_key == "list-svc-0"


async def test_list_payments_respects_limit_and_offset(session: AsyncSession) -> None:
    for index in range(5):
        await create_or_get_payment(
            session,
            sample_payment_create(description=f"paginated #{index}"),
            idempotency_key=f"pag-svc-{index}",
        )

    page = await list_payments(session, limit=2, offset=1)
    assert len(page) == 2
    assert page[0].idempotency_key == "pag-svc-3"
