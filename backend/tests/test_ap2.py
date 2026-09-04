import datetime

import pytest

from app import ap2, checkout
from app.models import AuditLog, CartMandateRecord


@pytest.fixture()
def fake_razorpay(monkeypatch):
    from app import razorpay_client

    calls = {"create_order": 0}
    counter = iter(range(1, 100))

    def fake_create_order(amount_paise, currency, receipt):
        calls["create_order"] += 1
        return {"id": f"order_ap2_{next(counter)}", "amount": amount_paise, "currency": currency}

    def fake_create_payment_link(amount_paise, description, reference_id):
        return {"short_url": f"https://rzp.io/l/ap2_{reference_id[:8]}"}

    monkeypatch.setattr(razorpay_client, "create_order", fake_create_order)
    monkeypatch.setattr(razorpay_client, "create_payment_link", fake_create_payment_link)
    return calls


def test_create_cart_mandate_locks_canonical_price(db_session):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 2}])
    assert mandate.total_inr == 799 * 2
    assert mandate.id.startswith("chk_")
    assert mandate.merchant_authorization.startswith("mock_merchant_sig_")

    record = db_session.query(CartMandateRecord).filter(CartMandateRecord.id == mandate.id).one()
    assert record.status == "open"
    assert record.total_inr == 799 * 2


def test_create_cart_mandate_refuses_when_mandate_check_fails(db_session):
    # 10 mechanical keyboards at 2999 each vastly exceeds the 5000 mandate
    with pytest.raises(ap2.CartMandateError, match="cart mandate refused"):
        ap2.create_cart_mandate(db_session, [{"product_id": 2, "qty": 10}])

    assert db_session.query(CartMandateRecord).count() == 0


def test_create_cart_mandate_refuses_unknown_product(db_session):
    with pytest.raises(ap2.CartMandateError):
        ap2.create_cart_mandate(db_session, [{"product_id": 99999, "qty": 1}])


def test_to_ap2_dict_matches_spec_shape(db_session):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    d = mandate.to_ap2_dict()
    contents = d["ap2"]["cart_mandate"]["contents"]
    assert contents["total"]["amount"]["value"] == 799
    assert contents["total"]["amount"]["currency"] == "INR"
    assert "cart_expiry" in contents
    assert d["ap2"]["cart_mandate"]["merchant_authorization"] == mandate.merchant_authorization


def test_complete_checkout_happy_path_creates_real_order(db_session, fake_razorpay):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    payment_mandate = {
        "mandate_id": "pm_1",
        "cart_reference": mandate.id,
        "total": {"value": mandate.total_inr},
        "user_authorization": ap2.expected_user_authorization("pm_1", mandate.id),
    }

    result = ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)

    assert result.allowed is True
    assert result.checkout_url is not None
    assert fake_razorpay["create_order"] == 1

    record = db_session.query(CartMandateRecord).filter(CartMandateRecord.id == mandate.id).one()
    assert record.status == "completed"


def test_complete_checkout_rejects_wrong_user_authorization(db_session, fake_razorpay):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    payment_mandate = {
        "mandate_id": "pm_1",
        "cart_reference": mandate.id,
        "total": {"value": mandate.total_inr},
        "user_authorization": "0" * 64,  # wrong signature
    }

    with pytest.raises(ap2.PaymentMandateError, match="user_authorization is invalid"):
        ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)

    assert fake_razorpay["create_order"] == 0

    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.session_id == f"ucp:{mandate.id}", AuditLog.event_type == "rejected_injection")
        .one()
    )
    assert row.status == "blocked"
    assert "invalid PaymentMandate signature" in row.llm_rationale


def test_complete_checkout_rejects_tampered_total(db_session, fake_razorpay):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    payment_mandate = {
        "mandate_id": "pm_1",
        "cart_reference": mandate.id,
        "total": {"value": 1},  # attacker tries to pay ₹1 for a ₹799 cart
        "user_authorization": ap2.expected_user_authorization("pm_1", mandate.id),
    }

    with pytest.raises(ap2.PaymentMandateError, match="does not match locked cart total"):
        ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)

    assert fake_razorpay["create_order"] == 0

    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.session_id == f"ucp:{mandate.id}", AuditLog.event_type == "rejected_injection")
        .one()
    )
    assert row.status == "blocked"
    assert '"submitted_total_inr": 1' in row.llm_said_json
    assert '"locked_total_inr": 799' in row.server_used_json


def test_complete_checkout_rejects_mismatched_cart_reference(db_session, fake_razorpay):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    payment_mandate = {
        "mandate_id": "pm_1",
        "cart_reference": "chk_some_other_cart",
        "total": {"value": mandate.total_inr},
        "user_authorization": ap2.expected_user_authorization("pm_1", "chk_some_other_cart"),
    }

    with pytest.raises(ap2.PaymentMandateError, match="cart_reference does not match"):
        ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)


def test_complete_checkout_rejects_expired_cart(db_session, fake_razorpay):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    record = db_session.query(CartMandateRecord).filter(CartMandateRecord.id == mandate.id).one()
    record.expires_at = record.expires_at - datetime.timedelta(hours=1)
    db_session.commit()

    payment_mandate = {
        "mandate_id": "pm_1",
        "cart_reference": mandate.id,
        "total": {"value": mandate.total_inr},
        "user_authorization": ap2.expected_user_authorization("pm_1", mandate.id),
    }

    with pytest.raises(ap2.PaymentMandateError, match="has expired"):
        ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)

    db_session.refresh(record)
    assert record.status == "expired"


def test_cart_mandate_cannot_be_completed_twice(db_session, fake_razorpay):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    payment_mandate = {
        "mandate_id": "pm_1",
        "cart_reference": mandate.id,
        "total": {"value": mandate.total_inr},
        "user_authorization": ap2.expected_user_authorization("pm_1", mandate.id),
    }
    ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)

    with pytest.raises(ap2.PaymentMandateError, match="is not open"):
        ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)

    assert fake_razorpay["create_order"] == 1  # not a second time


def test_complete_checkout_writes_ucp_session_audit_trail(db_session, fake_razorpay):
    mandate = ap2.create_cart_mandate(db_session, [{"product_id": 1, "qty": 1}])
    payment_mandate = {
        "mandate_id": "pm_1",
        "cart_reference": mandate.id,
        "total": {"value": mandate.total_inr},
        "user_authorization": ap2.expected_user_authorization("pm_1", mandate.id),
    }
    ap2.complete_checkout(db_session, cart_reference=mandate.id, payment_mandate=payment_mandate)

    rows = db_session.query(AuditLog).filter(AuditLog.session_id == f"ucp:{mandate.id}").all()
    assert any(r.event_type == "order_created" and r.status == "ok" for r in rows)
