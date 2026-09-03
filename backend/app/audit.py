import json

from sqlalchemy.orm import Session

from app.models import AuditLog


def log(
    db: Session,
    *,
    session_id: str,
    event_type: str,
    status: str,
    llm_rationale: str | None = None,
    llm_said: dict | None = None,
    server_used: dict | None = None,
    canonical_price_inr: int | None = None,
    mandate_check_result: str = "na",
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
    idempotency_key: str | None = None,
) -> AuditLog:
    row = AuditLog(
        session_id=session_id,
        event_type=event_type,
        status=status,
        llm_rationale=llm_rationale,
        llm_said_json=json.dumps(llm_said) if llm_said is not None else None,
        server_used_json=json.dumps(server_used) if server_used is not None else None,
        canonical_price_inr=canonical_price_inr,
        mandate_check_result=mandate_check_result,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        idempotency_key=idempotency_key,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_status(
    db: Session,
    row: AuditLog,
    *,
    status: str,
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
) -> AuditLog:
    row.status = status
    if razorpay_order_id is not None:
        row.razorpay_order_id = razorpay_order_id
    if razorpay_payment_id is not None:
        row.razorpay_payment_id = razorpay_payment_id
    db.commit()
    db.refresh(row)
    return row
