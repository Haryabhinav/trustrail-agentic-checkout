"""Tokenized recurring charge: an agent-initiated purchase with zero human interaction, once
a card is saved. RBI requires a second auth factor on a card's first transaction, so one
human-authenticated Checkout.js payment is unavoidable to tokenize the card; every charge
after that goes through charge_via_token with no checkout page, no OTP — gated by the same
app.mandate.check_mandate spend/category check as every other purchase path.
"""
import time

from sqlalchemy.orm import Session

from app import audit, config, razorpay_client
from app.models import SavedPaymentToken


class AutopayError(ValueError):
    pass


AUTHORIZATION_AMOUNT_PAISE = 100  # ₹1 — a nominal charge whose only purpose is to tokenize the card


def _get_or_create_row(db: Session) -> SavedPaymentToken:
    row = db.query(SavedPaymentToken).filter(SavedPaymentToken.id == 1).one_or_none()
    if row is None:
        row = SavedPaymentToken(id=1, razorpay_customer_id="", customer_email="", customer_contact="", status="none")
        db.add(row)
        db.commit()
    return row


def get_status(db: Session) -> dict:
    row = _get_or_create_row(db)
    return {
        "status": row.status,
        "card_last4": row.card_last4,
        "card_network": row.card_network,
    }


def is_active(db: Session) -> bool:
    row = _get_or_create_row(db)
    return row.status == "active" and bool(row.token_id)


def setup_authorization(db: Session, *, name: str, email: str, contact: str) -> dict:
    """Creates a Razorpay customer + a token-enabled order. The frontend opens Razorpay
    Checkout.js against this order; the human completes ONE authenticated payment; the result
    is handed to confirm_authorization below."""
    customer = razorpay_client.create_customer(name, email, contact)

    max_amount_paise = config.MANDATE_MAX_SPEND_INR * 100
    expire_at = int(time.time()) + 365 * 24 * 60 * 60  # 1 year out

    order = razorpay_client.create_authorization_order(
        amount_paise=AUTHORIZATION_AMOUNT_PAISE,
        customer_id=customer["id"],
        max_amount_paise=max_amount_paise,
        expire_at=expire_at,
    )

    row = _get_or_create_row(db)
    row.razorpay_customer_id = customer["id"]
    row.customer_email = email
    row.customer_contact = contact
    row.token_id = None
    row.status = "pending"
    db.commit()

    audit.log(
        db,
        session_id="autopay",
        event_type="autopay_setup_started",
        status="pending",
        canonical_price_inr=AUTHORIZATION_AMOUNT_PAISE // 100,
    )

    return {
        "key_id": config.RAZORPAY_KEY_ID,
        "order_id": order["id"],
        "amount_paise": AUTHORIZATION_AMOUNT_PAISE,
        "currency": "INR",
        "customer_id": customer["id"],
        "name": name,
        "email": email,
        "contact": contact,
    }


def confirm_authorization(db: Session, *, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> dict:
    if not razorpay_client.verify_checkout_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        audit.log(
            db,
            session_id="autopay",
            event_type="rejected_injection",
            status="blocked",
            llm_rationale="[autopay] checkout signature verification failed on confirm_authorization",
        )
        raise AutopayError("checkout signature verification failed")

    payment = razorpay_client.fetch_payment(razorpay_payment_id)
    token_id = payment.get("token_id")
    if not token_id:
        raise AutopayError("payment did not return a token_id — card was not tokenized")

    card = payment.get("card") or {}

    row = _get_or_create_row(db)
    row.token_id = token_id
    row.card_last4 = card.get("last4")
    row.card_network = card.get("network")
    row.status = "active"
    db.commit()

    audit.log(
        db,
        session_id="autopay",
        event_type="autopay_token_saved",
        status="ok",
        server_used={"card_network": row.card_network, "card_last4": row.card_last4},
    )

    return get_status(db)


def revoke(db: Session) -> dict:
    row = _get_or_create_row(db)
    row.status = "revoked"
    db.commit()
    audit.log(db, session_id="autopay", event_type="autopay_revoked", status="ok")
    return get_status(db)


def charge_via_token(db: Session, *, amount_inr: int, description: str) -> dict:
    """The zero-human-interaction charge. Caller (app.checkout.propose_and_autocharge) is
    responsible for having already run price_cart + check_mandate — this function only moves
    money, it does not re-derive whether it should."""
    row = _get_or_create_row(db)
    if row.status != "active" or not row.token_id:
        raise AutopayError("no active autopay token — call setup_authorization first")

    order = razorpay_client.create_order(amount_paise=amount_inr * 100, currency="INR", receipt=f"autopay-{int(time.time())}"[:40])
    payment = razorpay_client.charge_recurring(
        customer_id=row.razorpay_customer_id,
        token_id=row.token_id,
        order_id=order["id"],
        amount_paise=amount_inr * 100,
        email=row.customer_email,
        contact=row.customer_contact,
    )
    return {"order_id": order["id"], "payment_id": payment.get("id"), "status": payment.get("status")}
