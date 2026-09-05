import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import autopay
from app.db import get_db

router = APIRouter()
logger = logging.getLogger("paypilot.autopay")


class SetupRequest(BaseModel):
    name: str
    email: str
    contact: str


class ConfirmRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/autopay/setup")
def setup(req: SetupRequest, db: Session = Depends(get_db)):
    """Returns what the frontend needs to open Razorpay Checkout.js for the one, human-
    authenticated authorization payment that tokenizes the card."""
    try:
        return autopay.setup_authorization(db, name=req.name, email=req.email, contact=req.contact)
    except Exception as exc:  # noqa: BLE001 - clean error instead of a raw 500
        logger.exception("autopay setup_authorization failed")
        raise HTTPException(status_code=502, detail=f"could not start autopay setup: {exc}")


@router.post("/autopay/confirm")
def confirm(req: ConfirmRequest, db: Session = Depends(get_db)):
    """Called by the frontend's Checkout.js success handler. Verifies the payment signature
    server-side (never trusts the browser callback alone) before saving the token."""
    try:
        return {"ok": True, **autopay.confirm_authorization(
            db,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_signature=req.razorpay_signature,
        )}
    except autopay.AutopayError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - e.g. a Razorpay fetch_payment API failure
        logger.exception("autopay confirm_authorization failed")
        return {"ok": False, "error": f"could not confirm autopay setup: {exc}"}


@router.get("/autopay/status")
def status(db: Session = Depends(get_db)):
    return autopay.get_status(db)


@router.post("/autopay/revoke")
def revoke(db: Session = Depends(get_db)):
    return autopay.revoke(db)
