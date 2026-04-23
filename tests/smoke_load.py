from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

import httpx

BASE_URL = "http://localhost:8000"
API_KEY = "dev-secret-key"
PAYMENTS_COUNT = 30
CONCURRENCY = 10
POLL_INTERVAL_SECONDS = 1.0
WAIT_TIMEOUT_SECONDS = 45.0
WEBHOOK_URL = "https://httpbin.org/post"


@dataclass
class CreatedPayment:
    payment_id: str
    idempotency_key: str


async def create_one_payment(
    client: httpx.AsyncClient,
    index: int,
) -> CreatedPayment:
    idempotency_key = f"smoke-{uuid.uuid4()}"
    payload = {
        "amount": str(Decimal("100.00") + Decimal(index)),
        "currency": "RUB",
        "description": f"Smoke payment #{index}",
        "metadata": {"test_case": "smoke_load", "index": index},
        "webhook_url": WEBHOOK_URL,
    }
    response = await client.post(
        f"{BASE_URL}/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": idempotency_key,
        },
        json=payload,
    )
    response.raise_for_status()
    body = response.json()
    return CreatedPayment(
        payment_id=body["payment_id"], idempotency_key=idempotency_key
    )


async def fetch_status(client: httpx.AsyncClient, payment_id: str) -> str:
    response = await client.get(
        f"{BASE_URL}/api/v1/payments/{payment_id}",
        headers={"X-API-Key": API_KEY},
    )
    response.raise_for_status()
    return response.json()["status"]


async def create_batch() -> list[CreatedPayment]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=20.0) as client:

        async def wrapped(index: int) -> CreatedPayment:
            async with semaphore:
                return await create_one_payment(client=client, index=index)

        tasks = [wrapped(i) for i in range(PAYMENTS_COUNT)]
        return await asyncio.gather(*tasks)


async def wait_final_statuses(created: list[CreatedPayment]) -> dict[str, str]:
    deadline = asyncio.get_running_loop().time() + WAIT_TIMEOUT_SECONDS
    statuses: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=20.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            pending_ids: list[str] = []
            for item in created:
                status = await fetch_status(client=client, payment_id=item.payment_id)
                statuses[item.payment_id] = status
                if status == "pending":
                    pending_ids.append(item.payment_id)

            if not pending_ids:
                return statuses
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return statuses


async def main() -> None:
    print(f"[smoke] creating {PAYMENTS_COUNT} payments...")
    created = await create_batch()
    print(f"[smoke] created: {len(created)}")

    statuses = await wait_final_statuses(created)
    counts = Counter(statuses.values())

    print("[smoke] status summary:")
    print(f"  succeeded: {counts.get('succeeded', 0)}")
    print(f"  failed:    {counts.get('failed', 0)}")
    print(f"  pending:   {counts.get('pending', 0)}")
    print("[smoke] done")


if __name__ == "__main__":
    asyncio.run(main())
