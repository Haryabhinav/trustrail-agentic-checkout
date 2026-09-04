import pytest

from app import autopay, razorpay_client
from app.models import AuditLog, SavedPaymentToken


@pytest.fixture()
def fake_razorpay(monkeypatch):
    state = {"orders": 0, "recurring_charges": 0}

    def fake_create_customer(name, email, contact):
        return {"id": "cust_fake1", "name": name, "email": email, "contact": contact}

    def fake_create_authorization_order(amount_paise, customer_id, max_amount_paise, expire_at):
        state["orders"] += 1
        return {"id": "order_auth_1", "amount": amount_paise, "token": {"max_amount": max_amount_paise}}

    def fake_verify_checkout_signature(order_id, payment_id, signature):
        return signature == "valid_signature"

    def fake_fetch_payment(payment_id):
        return {"id": payment_id, "token_id": "token_fake1", "card": {"last4": "1007", "network": "Visa"}}

    def fake_create_order(amount_paise, currency, receipt):
        state["orders"] += 1
        return {"id": f"order_charge_{state['orders']}", "amount": amount_paise, "currency": currency}

    def fake_charge_recurring(*, customer_id, token_id, order_id, amount_paise, email, contact):
        state["recurring_charges"] += 1
        return {"id": f"pay_recurring_{state['recurring_charges']}", "status": "captured"}

    monkeypatch.setattr(razorpay_client, "create_customer", fake_create_customer)
    monkeypatch.setattr(razorpay_client, "create_authorization_order", fake_create_authorization_order)
    monkeypatch.setattr(razorpay_client, "verify_checkout_signature", fake_verify_checkout_signature)
    monkeypatch.setattr(razorpay_client, "fetch_payment", fake_fetch_payment)
    monkeypatch.setattr(razorpay_client, "create_order", fake_create_order)
    monkeypatch.setattr(razorpay_client, "charge_recurring", fake_charge_recurring)
    return state


def test_status_defaults_to_none(db_session):
    assert autopay.get_status(db_session) == {"status": "none", "card_last4": None, "card_network": None}
    assert autopay.is_active(db_session) is False


def test_setup_authorization_creates_customer_and_pending_token(db_session, fake_razorpay):
    result = autopay.setup_authorization(db_session, name="Test User", email="t@example.com", contact="9812345670")
    assert result["order_id"] == "order_auth_1"
    assert result["customer_id"] == "cust_fake1"

    row = db_session.query(SavedPaymentToken).filter(SavedPaymentToken.id == 1).one()
    assert row.status == "pending"
    assert row.razorpay_customer_id == "cust_fake1"


def test_confirm_authorization_activates_token(db_session, fake_razorpay):
    autopay.setup_authorization(db_session, name="Test User", email="t@example.com", contact="9812345670")

    result = autopay.confirm_authorization(
        db_session,
        razorpay_order_id="order_auth_1",
        razorpay_payment_id="pay_auth_1",
        razorpay_signature="valid_signature",
    )
    assert result["status"] == "active"
    assert result["card_last4"] == "1007"
    assert autopay.is_active(db_session) is True


def test_confirm_authorization_rejects_bad_signature(db_session, fake_razorpay):
    autopay.setup_authorization(db_session, name="Test User", email="t@example.com", contact="9812345670")

    with pytest.raises(autopay.AutopayError, match="signature verification failed"):
        autopay.confirm_authorization(
            db_session,
            razorpay_order_id="order_auth_1",
            razorpay_payment_id="pay_auth_1",
            razorpay_signature="wrong_signature",
        )
    assert autopay.is_active(db_session) is False

    row = db_session.query(AuditLog).filter(AuditLog.event_type == "rejected_injection").one()
    assert row.status == "blocked"


def test_charge_via_token_requires_active_status(db_session, fake_razorpay):
    with pytest.raises(autopay.AutopayError, match="no active autopay token"):
        autopay.charge_via_token(db_session, amount_inr=100, description="test")


def test_charge_via_token_moves_money_with_no_human_step(db_session, fake_razorpay):
    autopay.setup_authorization(db_session, name="Test User", email="t@example.com", contact="9812345670")
    autopay.confirm_authorization(
        db_session, razorpay_order_id="order_auth_1", razorpay_payment_id="pay_auth_1", razorpay_signature="valid_signature"
    )

    result = autopay.charge_via_token(db_session, amount_inr=799, description="test purchase")
    assert result["status"] == "captured"
    assert fake_razorpay["recurring_charges"] == 1


def test_revoke_disables_autopay(db_session, fake_razorpay):
    autopay.setup_authorization(db_session, name="Test User", email="t@example.com", contact="9812345670")
    autopay.confirm_authorization(
        db_session, razorpay_order_id="order_auth_1", razorpay_payment_id="pay_auth_1", razorpay_signature="valid_signature"
    )
    assert autopay.is_active(db_session) is True

    autopay.revoke(db_session)
    assert autopay.is_active(db_session) is False

    with pytest.raises(autopay.AutopayError):
        autopay.charge_via_token(db_session, amount_inr=100, description="should fail")
