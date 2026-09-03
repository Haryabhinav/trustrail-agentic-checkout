from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog

router = APIRouter()


@router.get("/audit")
def get_audit(limit: int = 100, db: Session = Depends(get_db)):
    rows = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "event_type": r.event_type,
            "llm_rationale": r.llm_rationale,
            "llm_said": r.llm_said_json,
            "server_used": r.server_used_json,
            "canonical_price_inr": r.canonical_price_inr,
            "mandate_check_result": r.mandate_check_result,
            "razorpay_order_id": r.razorpay_order_id,
            "razorpay_payment_id": r.razorpay_payment_id,
            "idempotency_key": r.idempotency_key,
            "status": r.status,
        }
        for r in rows
    ]
