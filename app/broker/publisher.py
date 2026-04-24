import asyncio
import logging
from datetime import datetime, timezone

from faststream.rabbit import RabbitBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.topology import PAYMENTS_EXCHANGE
from app.db.models import Outbox, OutboxStatus
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self, broker: RabbitBroker, poll_interval_seconds: int = 1) -> None:
        self._broker = broker
        self._poll_interval_seconds = poll_interval_seconds
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        await self._broker.start()

    async def stop(self) -> None:
        self._stopped.set()
        await self._broker.close()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self._publish_pending_batch()
            except Exception:
                logger.exception("Outbox publisher batch failed")
            await asyncio.sleep(self._poll_interval_seconds)

    async def _publish_pending_batch(self) -> None:
        async with SessionLocal() as session:
            rows = await self._fetch_pending(session)
            if not rows:
                return

            for event in rows:
                try:
                    await self._broker.publish(
                        message=event.payload,
                        routing_key=event.topic,
                        exchange=PAYMENTS_EXCHANGE,
                    )
                    event.status = OutboxStatus.published
                    event.published_at = datetime.now(tz=timezone.utc)
                    event.last_error = None
                except Exception as exc:
                    event.attempt_count += 1
                    event.last_error = str(exc)

            await session.commit()

    async def _fetch_pending(self, session: AsyncSession) -> list[Outbox]:
        result = await session.scalars(
            select(Outbox)
            .where(Outbox.status == OutboxStatus.pending)
            .order_by(Outbox.created_at.asc())
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        return list(result)
