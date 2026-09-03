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

    payload = json.loads(raw_body)
    event_id = payload.get("id") or request.headers.get("x-razorpay-event-id", "")
    event = payload.get("event", "")

    if not event_id:
        # Razorpay always sends an id in practice; refuse to dedupe on an empty key rather
        # than let multiple distinct id-less events collide on the same ProcessedWebhookEvent
        # primary key and silently drop all but the first.
        raise HTTPException(status_code=400, detail="webhook payload missing an event id")

    # Dedupe BEFORE any side effect (spend increment or audit write) — insert-or-ignore on the
    # event id. A replayed webhook becomes a no-op after the first successful insert. This is
    # what actually protects spent_so_far_inr from double-counting, not just logging dedup.
    already_processed = (
        db.query(ProcessedWebhookEvent).filter(ProcessedWebhookEvent.razorpay_event_id == event_id).one_or_none()
    )
    if already_processed is not None:
        return {"status": "duplicate, ignored"}

    db.add(ProcessedWebhookEvent(razorpay_event_id=event_id))
    db.commit()

    if event == "payment.captured":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        amount_inr = int(payment.get("amount", 0)) // 100
        order_id = payment.get("order_id")
        payment_id = payment.get("id")

        mandate = db.query(Mandate).filter(Mandate.id == 1).one_or_none()
        if mandate is not None:
            mandate.spent_so_far_inr += amount_inr
            db.commit()

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
