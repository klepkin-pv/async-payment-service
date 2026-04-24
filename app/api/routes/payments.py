import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.payment import PaymentAccepted, PaymentCreate, PaymentResponse
from app.services.payments import create_or_get_payment, get_payment, list_payments

router = APIRouter(prefix="/payments", tags=["payments"])


def map_payment_response(payment) -> PaymentResponse:
    return PaymentResponse(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.metadata_json,
        status=payment.status,
        webhook_url=payment.webhook_url,
        idempotency_key=payment.idempotency_key,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )


@router.post("", response_model=PaymentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
    body: PaymentCreate,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentAccepted:
    payment = await create_or_get_payment(
        session, body, idempotency_key=idempotency_key
    )
    response.status_code = status.HTTP_202_ACCEPTED

    return PaymentAccepted(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment_details(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> PaymentResponse:
    payment = await get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )
    return map_payment_response(payment)


@router.get("", response_model=list[PaymentResponse])
async def get_payments_list(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[PaymentResponse]:
    payments = await list_payments(session, limit=limit, offset=offset)
    return [map_payment_response(payment) for payment in payments]
