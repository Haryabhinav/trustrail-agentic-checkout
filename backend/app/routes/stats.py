from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app import autopay
from app.db import get_db
from app.models import AuditLog, Mandate

router = APIRouter()

_ORDER_EVENT_TYPES = ("order_created", "autopay_charge")


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Backs the dashboard's mandate meter and stat tiles with real DB numbers."""
    mandate = db.query(Mandate).filter(Mandate.id == 1).one()

    orders_count, blocked_count = db.query(
        func.sum(case((AuditLog.event_type.in_(_ORDER_EVENT_TYPES) & (AuditLog.status == "ok"), 1), else_=0)),
        func.sum(case((AuditLog.status == "blocked", 1), else_=0)),
    ).one()

    return {
        "max_spend_inr": mandate.max_spend_inr,
        "spent_so_far_inr": mandate.spent_so_far_inr,
        "allowed_categories": [c.strip() for c in mandate.allowed_categories.split(",")],
        "orders_count": orders_count or 0,
        "blocked_count": blocked_count or 0,
        "autopay_status": autopay.get_status(db)["status"],
    }
