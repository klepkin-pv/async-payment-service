import asyncio
import random
from datetime import datetime, timezone
from uuid import UUID

import httpx
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from sqlalchemy import select

from app.broker.topology import (
    PAYMENTS_DLQ_EXCHANGE,
    PAYMENTS_DLQ_ROUTING_KEY,
    PAYMENTS_NEW_QUEUE,
)
from app.core.config import get_settings
from app.db.models import Payment, PaymentStatus
from app.db.session import SessionLocal

settings = get_settings()
broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)


async def send_webhook_with_retries(webhook_url: str, payload: dict) -> None:
    delays = [1, 2, 4]
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(3):
            try:
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()
                return
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(delays[attempt])

    assert last_error is not None
    raise last_error


async def send_to_dlq(message: dict, error: str) -> None:
    await broker.publish(
        {
            "error": error,
            "failed_at": datetime.now(tz=timezone.utc).isoformat(),
            "payload": message,
        },
        routing_key=PAYMENTS_DLQ_ROUTING_KEY,
        exchange=PAYMENTS_DLQ_EXCHANGE,
    )


@broker.subscriber(PAYMENTS_NEW_QUEUE)
async def process_payment(message: dict) -> None:
    payment_id = message.get("payment_id")
    if payment_id is None:
        await send_to_dlq(message, "Missing payment_id")
        return

    async with SessionLocal() as session:
        payment = await session.scalar(
            select(Payment).where(Payment.id == UUID(payment_id))
        )
        if payment is None:
            await send_to_dlq(message, "Payment not found")
            return

        await asyncio.sleep(random.uniform(2.0, 5.0))
        payment.status = (
            PaymentStatus.succeeded if random.random() < 0.9 else PaymentStatus.failed
        )
        payment.processed_at = datetime.now(tz=timezone.utc)
        await session.commit()

        webhook_payload = {
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "processed_at": payment.processed_at.isoformat()
            if payment.processed_at
            else None,
        }

        try:
            await send_webhook_with_retries(payment.webhook_url, webhook_payload)
        except Exception as exc:
            await send_to_dlq(message, f"Webhook delivery failed: {exc}")


if __name__ == "__main__":
    asyncio.run(app.run())
