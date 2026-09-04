"""AP2 (Agent Payments Protocol) mandate handling for the UCP/MCP surface.

CartMandate — merchant-signed, price-locked cart, created by create_checkout.
PaymentMandate — caller-signed authorization referencing a CartMandate, verified by
complete_checkout before any money moves.

Signing is a deterministic hash, not real asymmetric crypto — matches the fidelity of
Google's own reference codelab; production AP2 uses SD-JWT.

This is a different "mandate" from app/mandate.py's spend/category cap: PaymentMandate
proves who authorized the purchase, check_mandate proves it's within budget. Both are
enforced independently — see complete_checkout, which only calls propose_and_checkout after
the AP2 pair verifies.
"""
import datetime
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import audit, config
from app.checkout import CheckoutResult, propose_and_checkout
from app.mandate import MandateState, check_mandate
from app.models import CartMandateRecord, Mandate, utcnow
from app.pricing import InsufficientStockError, PricedCart, UnknownProductError, price_cart


class CartMandateError(ValueError):
    pass


class PaymentMandateError(ValueError):
    pass


def _sign_cart(cart_id: str, total_inr: int) -> str:
    message = f"{cart_id}:{total_inr}:INR".encode()
    return "mock_merchant_sig_" + hmac.new(config.AP2_MOCK_SIGNING_SECRET.encode(), message, hashlib.sha256).hexdigest()


def expected_user_authorization(mandate_id: str, cart_reference: str) -> str:
    """Matches the reference codelab's demo-fidelity signature: sha256(mandate_id +
    cart_reference). Verified by recomputing, never trusted from the caller."""
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
    """Reprices and mandate-checks before issuing a price lock — a cart that wouldn't be
    allowed to check out is never locked in the first place."""
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
    """Verifies the PaymentMandate against its CartMandate, then hands off to
    propose_and_checkout — the same disposal boundary a chat-originated purchase uses."""
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

    # Detects storage tampering: re-derive and compare our own signature.
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
