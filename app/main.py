import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from faststream.rabbit import RabbitBroker

from app.api.deps import verify_api_key
from app.api.routes import payments_router
from app.broker.publisher import OutboxPublisher
from app.broker.topology import PAYMENTS_DLQ_QUEUE, PAYMENTS_NEW_QUEUE
from app.core.config import get_settings

settings = get_settings()
broker = RabbitBroker(settings.rabbitmq_url)
publisher = OutboxPublisher(
    broker=broker,
    poll_interval_seconds=settings.outbox_poll_interval_seconds,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await publisher.start()
    await broker.declare_queue(PAYMENTS_NEW_QUEUE)
    await broker.declare_queue(PAYMENTS_DLQ_QUEUE)
    task = asyncio.create_task(publisher.run())
    try:
        yield
    finally:
        await publisher.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Async Payment Service", lifespan=lifespan)
app.include_router(
    payments_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key)],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
