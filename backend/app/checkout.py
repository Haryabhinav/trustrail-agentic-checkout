"""The disposal boundary. This is the ONLY place cart items become a Razorpay order.

Called from routes/chat.py (propose_cart tool) and routes/demo.py (failure demo).
Never called with, and never reads, any price/discount value the LLM produced.
"""
import hashlib
import json
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import audit, autopay, demo_state, razorpay_client
from app.mandate import MandateState, check_mandate
from app.models import IdempotencyKey, Mandate
from app.pricing import InsufficientStockError, PricedCart, UnknownProductError, price_cart

# Compressed retry ladder for the live demo. Real backoff would be 0s / 60s / 120s / 300s;
# we label the compression explicitly on screen per the README demo script.
RETRY_DELAYS_SECONDS = [0, 1, 2, 3]

# Razorpay's `receipt` (and reference_id) fields reject anything longer than ~40-56 chars
# depending on the field (confirmed live: order.create rejected a 64-char sha256 receipt with
# "the length must be no more than 56"). Our internal idempotency_key stays a full sha256
# hexdigest everywhere else (DB, audit trail) for collision safety; only the value handed to
# Razorpay itself is truncated.
RAZORPAY_RECEIPT_MAX_LEN = 40


def razorpay_receipt(idempotency_key: str) -> str:
    return idempotency_key[:RAZORPAY_RECEIPT_MAX_LEN]


def compute_idempotency_key(session_id: str, priced_cart: PricedCart) -> str:
    cart_repr = json.dumps(
        sorted((item["product_id"], item["qty"]) for item in priced_cart.items)
    )
    return hashlib.sha256(f"{session_id}:{cart_repr}".encode()).hexdigest()


def get_mandate_state(db: Session) -> Mandate:
    mandate = db.query(Mandate).filter(Mandate.id == 1).one_or_none()
    if mandate is None:
        raise RuntimeError("Mandate row not seeded — run seed.py")
    return mandate


class CheckoutResult:
    def __init__(self, *, allowed: bool, reason: str, priced_cart: PricedCart | None = None,
                 checkout_url: str | None = None, order_id: str | None = None,
                 llm_said: dict | None = None, payment_id: str | None = None,
                 charged_directly: bool = False):
        self.allowed = allowed
        self.reason = reason
        self.priced_cart = priced_cart
        self.checkout_url = checkout_url
        self.order_id = order_id
        self.llm_said = llm_said
        self.payment_id = payment_id
        # True when this purchase was completed by app.autopay.charge_via_token — no
        # checkout link was ever generated because no human interaction was needed.
        self.charged_directly = charged_directly


@dataclass
class _GateResult:
    priced_cart: PricedCart | None
    llm_said: dict
    early_exit: CheckoutResult | None  # set when the caller should return this immediately


def _reprice_and_gate(
    db: Session,
    *,
    session_id: str,
    llm_proposed_items: list[dict],
    llm_rationale: str | None,
) -> _GateResult:
    """Shared by propose_and_checkout and propose_and_autocharge: reprice from the canonical
    Product table, detect/reject hallucinated price or discount fields, and run the spend/
    category mandate gate. Both callers diverge only in HOW they execute an allowed purchase
    (checkout link vs. a silent tokenized charge) — never in whether one is allowed.

    llm_proposed_items are raw tool-call args from the model: [{"product_id", "qty",
    ...anything else, including a hallucinated "price" or "discount" field}]. Any field other
    than product_id/qty is discarded here and never reaches pricing.py's signature.
    """
    llm_said = {"items": llm_proposed_items}
    discount_fields = [item for item in llm_proposed_items if "discount" in item]
    price_fields = [item for item in llm_proposed_items if "price" in item and "discount" not in item]

    try:
        # A malformed/hallucinated tool call missing product_id is a data-shape error, not a
        # crash — it must land in the same "reported back to the model" path as an unknown
        # product id or bad quantity, so the .get() + explicit check happens inside this
        # try block rather than before it.
        clean_items = []
        for item in llm_proposed_items:
            if "product_id" not in item:
                raise ValueError(f"tool call item missing product_id: {item}")
            clean_items.append({"product_id": item["product_id"], "qty": item.get("qty", 1)})
        priced_cart = price_cart(db, clean_items)
    except (UnknownProductError, InsufficientStockError, ValueError) as exc:
        # A hallucinated product_id, an impossible quantity, or an out-of-stock request is
        # treated the same way as a failed mandate check: reported back to the model as a
        # tool result (so it can explain to the user), never raised as an unhandled 500.
        audit.log(
            db,
            session_id=session_id,
            event_type="mandate_check",
            status="blocked",
            llm_rationale=llm_rationale,
            llm_said=llm_said,
            mandate_check_result="fail",
        )
        return _GateResult(None, llm_said, CheckoutResult(allowed=False, reason=str(exc), llm_said=llm_said))

    # A "discount" field is treated as a semantic manipulation attempt (prompt injection /
    # jailbreak), not an innocent hallucination — it is never applied, and gets its own event
    # type so the dashboard can show it as a distinct, named block rather than folding it into
    # ordinary price correction noise.
    if discount_fields:
        audit.log(
            db,
            session_id=session_id,
            event_type="rejected_injection",
            status="blocked",
            llm_rationale=llm_rationale,
            llm_said=llm_said,
            server_used={"total_inr": priced_cart.total_inr, "items": priced_cart.items, "discount_applied": 0},
            canonical_price_inr=priced_cart.total_inr,
        )
    elif price_fields:
        audit.log(
            db,
            session_id=session_id,
            event_type="price_mismatch_corrected",
            status="ok",
            llm_rationale=llm_rationale,
            llm_said=llm_said,
            server_used={"total_inr": priced_cart.total_inr, "items": priced_cart.items},
            canonical_price_inr=priced_cart.total_inr,
        )

    mandate_row = get_mandate_state(db)
    mandate_state = MandateState(
        max_spend_inr=mandate_row.max_spend_inr,
        allowed_categories=[c.strip() for c in mandate_row.allowed_categories.split(",")],
        spent_so_far_inr=mandate_row.spent_so_far_inr,
    )
    allowed, reason = check_mandate(priced_cart.total_inr, priced_cart.category, mandate_state)

    audit.log(
        db,
        session_id=session_id,
        event_type="mandate_check",
        status="ok" if allowed else "blocked",
        llm_rationale=llm_rationale,
        llm_said=llm_said,
        server_used={"total_inr": priced_cart.total_inr, "category": priced_cart.category},
        canonical_price_inr=priced_cart.total_inr,
        mandate_check_result="pass" if allowed else "fail",
    )

    if not allowed:
        return _GateResult(
            priced_cart, llm_said, CheckoutResult(allowed=False, reason=reason, priced_cart=priced_cart, llm_said=llm_said)
        )

    return _GateResult(priced_cart, llm_said, None)


def propose_and_checkout(
    db: Session,
    *,
    session_id: str,
    llm_proposed_items: list[dict],
    llm_rationale: str | None = None,
    sleep_fn=time.sleep,
) -> CheckoutResult:
    """Full server-side pipeline: reprice -> mandate check -> audit -> order -> payment link."""
    gate = _reprice_and_gate(db, session_id=session_id, llm_proposed_items=llm_proposed_items, llm_rationale=llm_rationale)
    if gate.early_exit is not None:
        return gate.early_exit
    priced_cart, llm_said = gate.priced_cart, gate.llm_said

    idempotency_key = compute_idempotency_key(session_id, priced_cart)

    existing = db.query(IdempotencyKey).filter(IdempotencyKey.key == idempotency_key).one_or_none()
    if existing is not None:
        return CheckoutResult(
            allowed=True,
            reason="already ordered (idempotent replay)",
            priced_cart=priced_cart,
            order_id=existing.razorpay_order_id,
            llm_said=llm_said,
        )

    pending_row = audit.log(
        db,
        session_id=session_id,
        event_type="order_created",
        status="pending",
        llm_rationale=llm_rationale,
        llm_said=llm_said,
        server_used={"total_inr": priced_cart.total_inr, "items": priced_cart.items},
        canonical_price_inr=priced_cart.total_inr,
        mandate_check_result="pass",
        idempotency_key=idempotency_key,
    )

    order = None
    last_error: Exception | None = None
    for attempt, delay in enumerate(RETRY_DELAYS_SECONDS):
        if delay:
            sleep_fn(delay)
        try:
            demo_state.maybe_fail()
            order = razorpay_client.create_order(
                amount_paise=priced_cart.total_inr * 100,
                currency="INR",
                receipt=razorpay_receipt(idempotency_key),
            )
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any gateway failure retries the same way
            last_error = exc
            audit.log(
                db,
                session_id=session_id,
                event_type="gateway_retry",
                status="retrying",
                llm_rationale=f"attempt {attempt + 1}/{len(RETRY_DELAYS_SECONDS)} failed: {exc}",
                idempotency_key=idempotency_key,
                canonical_price_inr=priced_cart.total_inr,
            )

    if order is None:
        audit.update_status(db, pending_row, status="error")
        return CheckoutResult(
            allowed=True,
            reason=f"payment gateway unavailable after {len(RETRY_DELAYS_SECONDS)} attempts: {last_error}",
            priced_cart=priced_cart,
            llm_said=llm_said,
        )

    # Record the order and its idempotency key as soon as it exists at Razorpay, before
    # attempting create_payment_link — so a failure in the next call can never leave an
    # order that exists at Razorpay with no trace of it in our own audit trail or
    # IdempotencyKey table (which would also risk a duplicate order on a naive retry).
    db.add(IdempotencyKey(key=idempotency_key, razorpay_order_id=order["id"]))
    audit.update_status(db, pending_row, status="pending", razorpay_order_id=order["id"])
    db.commit()

    try:
        link = razorpay_client.create_payment_link(
            amount_paise=priced_cart.total_inr * 100,
            description=f"TrustRail order {order['id']}",
            reference_id=razorpay_receipt(idempotency_key),
        )
    except Exception as exc:  # noqa: BLE001 - order exists; report the link failure, don't crash
        audit.update_status(db, pending_row, status="error", razorpay_order_id=order["id"])
        return CheckoutResult(
            allowed=True,
            reason=f"order {order['id']} was created but the payment link could not be generated: {exc}",
            priced_cart=priced_cart,
            order_id=order["id"],
            llm_said=llm_said,
        )

    audit.update_status(db, pending_row, status="ok", razorpay_order_id=order["id"])

    return CheckoutResult(
        allowed=True,
        reason="order created",
        priced_cart=priced_cart,
        checkout_url=link.get("short_url"),
        order_id=order["id"],
        llm_said=llm_said,
    )


def propose_and_autocharge(
    db: Session,
    *,
    session_id: str,
    llm_proposed_items: list[dict],
    llm_rationale: str | None = None,
) -> CheckoutResult:
    """The zero-human-interaction path: reprice -> mandate check -> audit -> silent tokenized
    charge via app.autopay. No checkout link is ever generated — there is nothing for a human
    to click, because there's a previously-authorized saved card to charge directly.

    Callers (routes/chat.py, routes/demo.py) are responsible for checking
    app.autopay.is_active(db) first and choosing this over propose_and_checkout — this
    function does not fall back to a checkout link if no token is active, it fails closed.
    """
    gate = _reprice_and_gate(db, session_id=session_id, llm_proposed_items=llm_proposed_items, llm_rationale=llm_rationale)
    if gate.early_exit is not None:
        return gate.early_exit
    priced_cart, llm_said = gate.priced_cart, gate.llm_said

    pending_row = audit.log(
        db,
        session_id=session_id,
        event_type="autopay_charge",
        status="pending",
        llm_rationale=llm_rationale,
        llm_said=llm_said,
        server_used={"total_inr": priced_cart.total_inr, "items": priced_cart.items},
        canonical_price_inr=priced_cart.total_inr,
        mandate_check_result="pass",
    )

    try:
        charge = autopay.charge_via_token(
            db, amount_inr=priced_cart.total_inr, description=f"TrustRail autopay charge ({session_id})"
        )
    except autopay.AutopayError as exc:
        audit.update_status(db, pending_row, status="error")
        return CheckoutResult(allowed=True, reason=f"autopay charge failed: {exc}", priced_cart=priced_cart, llm_said=llm_said)

    audit.update_status(db, pending_row, status="ok", razorpay_order_id=charge["order_id"])

    return CheckoutResult(
        allowed=True,
        reason="charged automatically via saved payment method — no human interaction required",
        priced_cart=priced_cart,
        order_id=charge["order_id"],
        payment_id=charge["payment_id"],
        charged_directly=True,
        llm_said=llm_said,
    )
