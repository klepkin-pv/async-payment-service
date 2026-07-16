from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Outbox, Payment, PaymentStatus
from tests.conftest import api_headers, is_valid_uuid, payment_payload

pytestmark = pytest.mark.asyncio


async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_create_payment_requires_api_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments",
        json=payment_payload(),
        headers={"Idempotency-Key": "idem-key-1"},
    )
    assert response.status_code == 422


async def test_create_payment_with_invalid_api_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments",
        json=payment_payload(),
        headers={"X-API-Key": "wrong-key", "Idempotency-Key": "idem-key-1"},
    )
    assert response.status_code == 401


async def test_create_payment_requires_idempotency_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments",
        json=payment_payload(),
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 422


async def test_create_payment_success(client: AsyncClient, session: AsyncSession) -> None:
    response = await client.post(
        "/api/v1/payments",
        json=payment_payload(),
        headers=api_headers("idem-key-1"),
    )
    assert response.status_code == 202
    body = response.json()
    assert is_valid_uuid(body["payment_id"])
    assert body["status"] == PaymentStatus.pending.value
    assert "created_at" in body

    payment = await session.scalar(select(Payment))
    assert payment is not None
    assert payment.amount == Decimal("100.50")
    assert payment.currency == "RUB"
    assert payment.idempotency_key == "idem-key-1"

    outbox = await session.scalar(select(Outbox))
    assert outbox is not None
    assert outbox.payload["payment_id"] == body["payment_id"]


async def test_create_payment_is_idempotent(client: AsyncClient) -> None:
    payload = payment_payload()
    response_1 = await client.post(
        "/api/v1/payments",
        json=payload,
        headers=api_headers("idem-key-2"),
    )
    assert response_1.status_code == 202
    payment_id_1 = response_1.json()["payment_id"]

    response_2 = await client.post(
        "/api/v1/payments",
        json=payment_payload(amount="999.00"),
        headers=api_headers("idem-key-2"),
    )
    assert response_2.status_code == 202
    assert response_2.json()["payment_id"] == payment_id_1


async def test_get_payment_details(client: AsyncClient, payment: Payment) -> None:
    response = await client.get(
        f"/api/v1/payments/{payment.id}",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["payment_id"] == str(payment.id)
    assert body["amount"] == "100.50"
    assert body["currency"] == "RUB"
    assert body["status"] == PaymentStatus.pending.value


async def test_get_payment_not_found(client: AsyncClient) -> None:
    response = await client.get(
        f"/api/v1/payments/{uuid4()}",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Payment not found"


async def test_list_payments(client: AsyncClient, payment: Payment) -> None:
    response = await client.get(
        "/api/v1/payments",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["payment_id"] == str(payment.id)


async def test_list_payments_pagination(client: AsyncClient, session: AsyncSession) -> None:
    for index in range(3):
        session.add(
            Payment(
                amount=Decimal(f"{index}.00"),
                currency="USD",
                description=f"Payment #{index}",
                metadata_json={},
                status=PaymentStatus.pending,
                idempotency_key=f"list-key-{index}",
                webhook_url="https://example.com/webhook",
            )
        )
    await session.commit()

    response = await client.get(
        "/api/v1/payments?limit=2&offset=0",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = await client.get(
        "/api/v1/payments?limit=2&offset=2",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
