from __future__ import annotations

import os
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from uuid import UUID

os.environ.setdefault("API_KEY", "test-secret-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/payments_test"
)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Outbox, OutboxStatus, Payment, PaymentStatus
from app.db.session import get_db_session
from app.main import app
from app.schemas.payment import PaymentCreate

DATABASE_URL = os.environ["DATABASE_URL"]


async def _lifespan_off_wrapper(scope: Any, receive: Any, send: Any) -> None:
    """ASGI wrapper that ignores lifespan events so tests don't need RabbitMQ."""
    if scope.get("type") == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        await app(scope, receive, send)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    transport = ASGITransport(app=_lifespan_off_wrapper)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.pop(get_db_session, None)


@pytest_asyncio.fixture
async def payment(session: AsyncSession) -> Payment:
    payload = PaymentCreate(
        amount=Decimal("100.50"),
        currency="RUB",
        description="Test payment",
        webhook_url="https://example.com/webhook",
    )
    payment = Payment(
        amount=payload.amount,
        currency=payload.currency.upper(),
        description=payload.description,
        metadata_json=payload.metadata,
        status=PaymentStatus.pending,
        idempotency_key="idem-key-1",
        webhook_url=str(payload.webhook_url),
    )
    outbox = Outbox(
        topic="payments.new",
        status=OutboxStatus.pending,
        payload={"payment_id": str(payment.id), "idempotency_key": "idem-key-1"},
    )
    session.add(payment)
    await session.flush()
    session.add(outbox)
    await session.commit()
    await session.refresh(payment)
    return payment


def payment_payload(amount: str = "100.50", **overrides: Any) -> dict[str, Any]:
    return {
        "amount": amount,
        "currency": "RUB",
        "description": "Test payment",
        "metadata": {"source": "pytest"},
        "webhook_url": "https://example.com/webhook",
        **overrides,
    }


def api_headers(idempotency_key: str = "idem-key-1") -> dict[str, str]:
    return {
        "X-API-Key": os.environ["API_KEY"],
        "Idempotency-Key": idempotency_key,
    }


def is_valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False
