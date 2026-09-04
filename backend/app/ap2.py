"""AP2 (Agent Payments Protocol) mandate handling for the UCP/MCP surface.

This is Google's real, published agentic-commerce spec (ap2-protocol.org), not an invented
analogy — relevant because Track 01 is literally "AI Growth & Agentic Commerce." Two mandate
types, exactly as the spec defines them:

  CartMandate    — merchant-signed, price-locked cart. Created by `create_checkout`.
  PaymentMandate — caller-signed authorization referencing a CartMandate. Submitted to
                   `complete_checkout`, which verifies both before any money moves.

Signing here is a deterministic hash, not real asymmetric cryptography — this matches the
fidelity of Google's own reference codelab (`merchant_authorization: "mock_merchant_sig_..."`,
`user_authorization: sha256(mandate_id + cart_reference)`); production AP2 uses SD-JWT.
Labeled honestly wherever it appears, including in the API responses themselves.

Note this is a DIFFERENT "mandate" concept from app/mandate.py's spend/category cap — an AP2
PaymentMandate proves *who authorized this specific purchase*; app/mandate.py's check_mandate
proves *the purchase is within the merchant's configured spend bounds*. Both are enforced,
independently, on the same request — see complete_checkout below, which re-runs
app.checkout.propose_and_checkout (spend/category gate + idempotent order creation) only
after the AP2 mandate pair verifies.
"""
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import audit, config
from app.checkout import CheckoutResult, propose_and_checkout
from app.models import CartMandateRecord
from app.pricing import InsufficientStockError, UnknownProductError, price_cart, PricedCart
from app.mandate import MandateState, check_mandate
from app.models import Mandate, utcnow
import datetime


class CartMandateError(ValueError):
    pass


class PaymentMandateError(ValueError):
    pass


def _sign_cart(cart_id: str, total_inr: int) -> str:
    """Mock merchant signature — a merchant re-derives and compares this, so any tampering
    with the cart id or total after issuance is detectable, even without real asymmetric
    crypto. This is exactly the property a CartMandate exists to provide."""
    message = f"{cart_id}:{total_inr}:INR".encode()
    return "mock_merchant_sig_" + hmac.new(config.AP2_MOCK_SIGNING_SECRET.encode(), message, hashlib.sha256).hexdigest()


def expected_user_authorization(mandate_id: str, cart_reference: str) -> str:
    """Matches Google's own reference codelab's demo-fidelity signature:
    sha256(mandate_id + cart_reference). A real caller (agent or SDK) computes this the same
    way; we verify by recomputing, not by trusting whatever string is handed to us."""
    return hashlib.sha256(f"{mandate_id}{cart_reference}".encode()).hexdigest()


@dataclass
class CartMandate:
    id: str
    merchant_name: str
    total_inr: int
    currency: str
    cart_expiry: str  # ISO8601
    merchant_authorization: str
    items: list[dict]

    def to_ap2_dict(self) -> dict:
        return {
            "ap2": {
                "cart_mandate": {
                    "contents": {
                        "id": self.id,
                        "merchant_name": self.merchant_name,
                        "total": {"label": "Total", "amount": {"currency": self.currency, "value": self.total_inr}},
                        "cart_expiry": self.cart_expiry,
                    },
                    "merchant_authorization": self.merchant_authorization,
                }
            }
        }


def create_cart_mandate(db: Session, items: list[dict], session_id: str = "ucp") -> CartMandate:
    """Reprices from the canonical Product table and runs the spend/category mandate check —
    same deterministic gate the chat agent's propose_cart uses — BEFORE issuing a price lock.
    A cart that wouldn't be allowed to check out is never issued a CartMandate in the first
    place, rather than being locked and rejected later at complete_checkout.
    """
    try:
        priced: PricedCart = price_cart(db, items)
    except (UnknownProductError, InsufficientStockError, ValueError) as exc:
        raise CartMandateError(str(exc)) from exc

    mandate_row = db.query(Mandate).filter(Mandate.id == 1).one()
    mandate_state = MandateState(
        max_spend_inr=mandate_row.max_spend_inr,
        allowed_categories=[c.strip() for c in mandate_row.allowed_categories.split(",")],
        spent_so_far_inr=mandate_row.spent_so_far_inr,
    )
    allowed, reason = check_mandate(priced.total_inr, priced.category, mandate_state)

    audit.log(
        db,
        session_id=session_id,
        event_type="mandate_check",
        status="ok" if allowed else "blocked",
        llm_said={"source": "ucp_mcp", "items": items},
        server_used={"total_inr": priced.total_inr, "category": priced.category},
        canonical_price_inr=priced.total_inr,
        mandate_check_result="pass" if allowed else "fail",
    )

    if not allowed:
        raise CartMandateError(f"cart mandate refused: {reason}")

    cart_id = "chk_" + uuid.uuid4().hex[:16]
    expires_at = utcnow() + datetime.timedelta(seconds=config.AP2_CART_MANDATE_TTL_SECONDS)
    signature = _sign_cart(cart_id, priced.total_inr)

    db.add(
        CartMandateRecord(
            id=cart_id,
            items_json=json.dumps(items),
            total_inr=priced.total_inr,
            category=priced.category,
            merchant_authorization=signature,
            expires_at=expires_at,
            status="open",
        )
    )
    db.commit()

    return CartMandate(
        id=cart_id,
        merchant_name=config.UCP_MERCHANT_NAME,
        total_inr=priced.total_inr,
        currency="INR",
        cart_expiry=expires_at.isoformat(),
        merchant_authorization=signature,
        items=priced.items,
    )


def get_cart_mandate(db: Session, cart_id: str) -> CartMandateRecord:
    record = db.query(CartMandateRecord).filter(CartMandateRecord.id == cart_id).one_or_none()
    if record is None:
        raise CartMandateError(f"no such cart mandate: {cart_id}")
    return record


def complete_checkout(db: Session, *, cart_reference: str, payment_mandate: dict) -> CheckoutResult:
    """Verifies the PaymentMandate against its referenced CartMandate, then — and only
    then — hands off to app.checkout.propose_and_checkout, which independently re-prices,
    re-runs the spend/category gate, and idempotently creates the Razorpay order. This means
    a UCP/AP2-originated purchase goes through the exact same disposal boundary as a chat-
    originated one; there is no second, weaker path to money movement.
    """
    record = get_cart_mandate(db, cart_reference)

    if record.status != "open":
        raise PaymentMandateError(f"cart mandate {cart_reference} is not open (status={record.status})")

    if record.expires_at.replace(tzinfo=datetime.timezone.utc) < utcnow():
        record.status = "expired"
        db.commit()
        raise PaymentMandateError(f"cart mandate {cart_reference} has expired")

    if payment_mandate.get("cart_reference") != cart_reference:
        raise PaymentMandateError("payment mandate cart_reference does not match")

    submitted_total = (payment_mandate.get("total") or {}).get("value")
    if submitted_total != record.total_inr:
        # Defends the CartMandate's core promise: the price cannot change between issuance
        # and completion. Whether the drift came from a stale client or a manipulation
        # attempt, the outcome is the same: refuse, don't guess which one it was — and, same
        # as the chat agent's injection path, this specific shape of failure (a caller trying
        # to substitute its own number for the locked one) gets its own audit row, visible on
        # the dashboard the same way a chat-side discount injection is.
        audit.log(
            db,
            session_id=f"ucp:{cart_reference}",
            event_type="rejected_injection",
            status="blocked",
            llm_rationale="[ucp/ap2] complete_checkout submitted a total that does not match the locked CartMandate",
            llm_said={"source": "ucp_mcp_payment_mandate", "submitted_total_inr": submitted_total},
            server_used={"locked_total_inr": record.total_inr},
            canonical_price_inr=record.total_inr,
        )
        raise PaymentMandateError(
            f"payment mandate total {submitted_total} does not match locked cart total {record.total_inr}"
        )

    mandate_id = payment_mandate.get("mandate_id", "")
    expected_sig = expected_user_authorization(mandate_id, cart_reference)
    if not hmac.compare_digest(payment_mandate.get("user_authorization", ""), expected_sig):
        audit.log(
            db,
            session_id=f"ucp:{cart_reference}",
            event_type="rejected_injection",
            status="blocked",
            llm_rationale="[ucp/ap2] complete_checkout submitted an invalid PaymentMandate signature",
            llm_said={"source": "ucp_mcp_payment_mandate", "mandate_id": mandate_id},
            server_used={"reason": "user_authorization did not match the expected signature"},
            canonical_price_inr=record.total_inr,
        )
        raise PaymentMandateError("payment mandate user_authorization is invalid")

    # Re-verify our own CartMandate signature too — if the record's stored signature doesn't
    # match what we'd sign for this id/total today, something in storage was tampered with.
    if not hmac.compare_digest(record.merchant_authorization, _sign_cart(record.id, record.total_inr)):
        raise CartMandateError("cart mandate merchant_authorization failed self-verification")

    record.status = "completed"
    db.commit()

    items = json.loads(record.items_json)
    return propose_and_checkout(
        db,
        session_id=f"ucp:{record.id}",
        llm_proposed_items=items,
        llm_rationale="[ucp/ap2] completed via MCP complete_checkout with a verified PaymentMandate",
    )
