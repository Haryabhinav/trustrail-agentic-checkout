from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import autopay
from app.db import get_db
from app.models import AuditLog, Mandate

router = APIRouter()


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Backs the dashboard's mandate meter and stat tiles with real numbers — the UI never
    computes or fakes these client-side."""
    mandate = db.query(Mandate).filter(Mandate.id == 1).one()
    orders_count = (
        db.query(AuditLog).filter(AuditLog.event_type.in_(["order_created", "autopay_charge"]), AuditLog.status == "ok").count()
    )
    blocked_count = db.query(AuditLog).filter(AuditLog.status == "blocked").count()

    return {
        "max_spend_inr": mandate.max_spend_inr,
        "spent_so_far_inr": mandate.spent_so_far_inr,
        "allowed_categories": [c.strip() for c in mandate.allowed_categories.split(",")],
        "orders_count": orders_count,
        "blocked_count": blocked_count,
        "autopay_status": autopay.get_status(db)["status"],
    }
