import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Outbox, OutboxStatus, Payment, PaymentStatus
from app.schemas.payment import PaymentCreate

PAYMENTS_NEW_TOPIC = "payments.new"


async def create_or_get_payment(
    session: AsyncSession, payload: PaymentCreate, idempotency_key: str
) -> Payment:
    existing = await session.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    if existing:
        return existing

    payment = Payment(
        amount=payload.amount,
        currency=payload.currency.upper(),
        description=payload.description,
        metadata_json=payload.metadata,
        status=PaymentStatus.pending,
        idempotency_key=idempotency_key,
        webhook_url=str(payload.webhook_url),
    )

    outbox = Outbox(
        topic=PAYMENTS_NEW_TOPIC,
        status=OutboxStatus.pending,
        payload={
            "payment_id": str(payment.id),
            "idempotency_key": idempotency_key,
        },
    )

    session.add(payment)
    await session.flush()

    outbox.payload["payment_id"] = str(payment.id)
    session.add(outbox)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        dedup = await session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        if dedup:
            return dedup
        raise

    await session.refresh(payment)
    return payment


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.id == payment_id))
