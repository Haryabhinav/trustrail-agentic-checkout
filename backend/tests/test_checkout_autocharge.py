import pytest

from app import autopay, checkout, razorpay_client
from app.models import AuditLog


@pytest.fixture()
def active_autopay(monkeypatch, db_session):
    """Sets up an already-active autopay token, mocking only the recurring-charge call —
    checkout.propose_and_autocharge should never touch create_order/create_payment_link."""
    monkeypatch.setattr(razorpay_client, "create_customer", lambda name, email, contact: {"id": "cust_1"})
    monkeypatch.setattr(
        razorpay_client, "create_authorization_order",
        lambda amount_paise, customer_id, max_amount_paise, expire_at: {"id": "order_auth_1"},
    )
    monkeypatch.setattr(razorpay_client, "verify_checkout_signature", lambda *a: True)
    monkeypatch.setattr(
        razorpay_client, "fetch_payment",
        lambda payment_id: {"id": payment_id, "token_id": "tok_1", "card": {"last4": "1007", "network": "Visa"}},
    )

    charges = {"n": 0}

    def fake_create_order(amount_paise, currency, receipt):
        charges["n"] += 1
        return {"id": f"order_{charges['n']}", "amount": amount_paise, "currency": currency}

    def fake_charge_recurring(**kwargs):
        return {"id": f"pay_{charges['n']}", "status": "captured"}

    monkeypatch.setattr(razorpay_client, "create_order", fake_create_order)
    monkeypatch.setattr(razorpay_client, "charge_recurring", fake_charge_recurring)

    autopay.setup_authorization(db_session, name="T", email="t@example.com", contact="9812345670")
    autopay.confirm_authorization(db_session, razorpay_order_id="order_auth_1", razorpay_payment_id="pay_auth_1", razorpay_signature="x")

    return charges


def test_autocharge_happy_path_charges_with_no_link(db_session, active_autopay):
    result = checkout.propose_and_autocharge(db_session, session_id="s1", llm_proposed_items=[{"product_id": 1, "qty": 1}])
    assert result.allowed is True
    assert result.charged_directly is True
    assert result.checkout_url is None
    assert result.payment_id is not None

    row = db_session.query(AuditLog).filter(AuditLog.event_type == "autopay_charge", AuditLog.session_id == "s1").one()
    assert row.status == "ok"
    assert row.canonical_price_inr == 799


def test_autocharge_still_enforces_mandate_gate(db_session, active_autopay):
    # 10 mechanical keyboards vastly exceeds the mandate — autopay must not bypass this
    result = checkout.propose_and_autocharge(db_session, session_id="s2", llm_proposed_items=[{"product_id": 2, "qty": 10}])
    assert result.allowed is False
    assert "exceeds remaining mandate budget" in result.reason
    assert active_autopay["n"] == 0  # no charge was even attempted


def test_autocharge_still_rejects_discount_injection(db_session, active_autopay):
    result = checkout.propose_and_autocharge(
        db_session, session_id="s3", llm_proposed_items=[{"product_id": 1, "qty": 1, "discount": "100%"}]
    )
    assert result.allowed is True
    assert result.charged_directly is True  # discount ignored, full price still auto-charged

    row = db_session.query(AuditLog).filter(AuditLog.event_type == "rejected_injection", AuditLog.session_id == "s3").one()
    assert row.status == "blocked"


def test_autocharge_without_active_token_fails_closed_gracefully(db_session):
    # No active token — must report a clear failure via CheckoutResult, never raise past the
    # disposal boundary (routes/chat.py and routes/demo.py both check autopay.is_active(db)
    # before calling this function, but the function itself must still fail safe on its own).
    result = checkout.propose_and_autocharge(db_session, session_id="s4", llm_proposed_items=[{"product_id": 1, "qty": 1}])
    assert result.allowed is True  # mandate allowed it; the charge mechanism is what failed
    assert result.charged_directly is False
    assert "autopay charge failed" in result.reason

    row = db_session.query(AuditLog).filter(AuditLog.event_type == "autopay_charge", AuditLog.session_id == "s4").one()
    assert row.status == "error"
