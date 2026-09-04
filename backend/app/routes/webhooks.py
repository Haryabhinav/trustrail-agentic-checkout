import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import audit, config
from app.db import get_db
from app.models import Mandate, ProcessedWebhookEvent
from app.razorpay_client import verify_webhook_signature

router = APIRouter()


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    if not verify_webhook_signature(raw_body, x_razorpay_signature, config.RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="malformed webhook body: not valid JSON")

    event_id = payload.get("id") or request.headers.get("x-razorpay-event-id", "")
    event = payload.get("event", "")

    if not event_id:
        # Avoid distinct id-less events colliding on the same dedup primary key.
        raise HTTPException(status_code=400, detail="webhook payload missing an event id")

    already_processed = (
        db.query(ProcessedWebhookEvent).filter(ProcessedWebhookEvent.razorpay_event_id == event_id).one_or_none()
    )
    if already_processed is not None:
        return {"status": "duplicate, ignored"}

    # Not committed yet — flushed together with the spend update and audit row below (inside
    # audit.log's commit), so a crash between them can't mark the event processed without
    # the spend update actually landing.
    db.add(ProcessedWebhookEvent(razorpay_event_id=event_id))

    if event == "payment.captured":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        try:
            amount_inr = int(payment.get("amount", 0)) // 100
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="malformed webhook payload: payment.amount is not numeric")
        order_id = payment.get("order_id")
        payment_id = payment.get("id")

        mandate = db.query(Mandate).filter(Mandate.id == 1).one_or_none()
        if mandate is not None:
            mandate.spent_so_far_inr += amount_inr

        audit.log(
            db,
            session_id="webhook",
            event_type="payment_captured",
            status="ok",
            canonical_price_inr=amount_inr,
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
        )
    else:
        audit.log(db, session_id="webhook", event_type="webhook_received", status="ok")

    return {"status": "ok"}
