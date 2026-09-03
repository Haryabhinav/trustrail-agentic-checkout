import itertools

import pytest

from app import checkout, demo_state, razorpay_client
from app.models import AuditLog, IdempotencyKey


@pytest.fixture(autouse=True)
def _reset_demo_state():
    demo_state.arm(0)
    yield
    demo_state.arm(0)


@pytest.fixture()
def fake_razorpay(monkeypatch):
    order_counter = itertools.count(1)
    calls = {"create_order": 0, "create_payment_link": 0, "receipts_seen": [], "reference_ids_seen": []}

    def fake_create_order(amount_paise, currency, receipt):
        calls["create_order"] += 1
        calls["receipts_seen"].append(receipt)
        return {"id": f"order_fake_{next(order_counter)}", "amount": amount_paise, "currency": currency}

    def fake_create_payment_link(amount_paise, description, reference_id):
        calls["create_payment_link"] += 1
        calls["reference_ids_seen"].append(reference_id)
        return {"short_url": f"https://rzp.io/l/fake_{reference_id[:8]}"}

    monkeypatch.setattr(razorpay_client, "create_order", fake_create_order)
    monkeypatch.setattr(razorpay_client, "create_payment_link", fake_create_payment_link)
    return calls


def test_happy_path_creates_order_and_returns_checkout_url(db_session, fake_razorpay):
    result = checkout.propose_and_checkout(
        db_session, session_id="s1", llm_proposed_items=[{"product_id": 1, "qty": 2}]
    )
    assert result.allowed is True
    assert result.checkout_url is not None
    assert result.order_id is not None
    assert fake_razorpay["create_order"] == 1
    assert fake_razorpay["create_payment_link"] == 1

    order_row = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "order_created", AuditLog.session_id == "s1")
        .one()
    )
    assert order_row.status == "ok"
    assert order_row.canonical_price_inr == 799 * 2


def test_receipt_and_reference_id_sent_to_razorpay_are_within_length_limits(db_session, fake_razorpay):
    # Real Razorpay order.create rejected a full 64-char sha256 receipt live with
    # "the length must be no more than 56" — this pins the truncation regression.
    result = checkout.propose_and_checkout(
        db_session, session_id="s_len", llm_proposed_items=[{"product_id": 1, "qty": 1}]
    )
    assert result.allowed is True
    assert len(fake_razorpay["receipts_seen"][0]) <= checkout.RAZORPAY_RECEIPT_MAX_LEN
    assert len(fake_razorpay["reference_ids_seen"][0]) <= checkout.RAZORPAY_RECEIPT_MAX_LEN
    # but the full, untruncated key is still what's stored internally for collision safety
    assert len(result.priced_cart and checkout.compute_idempotency_key("s_len", result.priced_cart)) == 64


def test_over_budget_cart_is_blocked_and_no_order_created(db_session, fake_razorpay):
    # 10 mechanical keyboards at 2999 each vastly exceeds the 5000 mandate
    result = checkout.propose_and_checkout(
        db_session, session_id="s2", llm_proposed_items=[{"product_id": 2, "qty": 10}]
    )
    assert result.allowed is False
    assert "exceeds remaining mandate budget" in result.reason
    assert fake_razorpay["create_order"] == 0

    check_row = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "mandate_check", AuditLog.session_id == "s2")
        .one()
    )
    assert check_row.status == "blocked"
    assert check_row.mandate_check_result == "fail"


def test_llm_price_never_used_even_if_supplied(db_session, fake_razorpay):
    # Model hallucinates a low price/large discount; server must reprice from the DB.
    result = checkout.propose_and_checkout(
        db_session,
        session_id="s3",
        llm_proposed_items=[{"product_id": 1, "qty": 1, "price": 1}],
    )
    assert result.priced_cart.total_inr == 799  # canonical DB price, not the hallucinated 1

    correction_row = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "price_mismatch_corrected", AuditLog.session_id == "s3")
        .one()
    )
    assert '"price": 1' in correction_row.llm_said_json
    assert "799" in correction_row.server_used_json


def test_discount_field_is_rejected_as_injection_not_applied(db_session, fake_razorpay):
    result = checkout.propose_and_checkout(
        db_session,
        session_id="s4",
        llm_proposed_items=[{"product_id": 1, "qty": 1, "discount": "100%"}],
    )
    assert result.priced_cart.total_inr == 799  # full price, discount ignored
    assert result.checkout_url is not None  # purchase still proceeds, just undiscounted

    injection_row = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "rejected_injection", AuditLog.session_id == "s4")
        .one()
    )
    assert injection_row.status == "blocked"
    assert "discount_applied" in injection_row.server_used_json


def test_idempotent_replay_does_not_create_a_second_order(db_session, fake_razorpay):
    items = [{"product_id": 1, "qty": 1}]
    first = checkout.propose_and_checkout(db_session, session_id="s5", llm_proposed_items=items)
    second = checkout.propose_and_checkout(db_session, session_id="s5", llm_proposed_items=items)

    assert first.order_id == second.order_id
    assert fake_razorpay["create_order"] == 1  # not called twice
    assert db_session.query(IdempotencyKey).count() == 1


def test_gateway_retries_then_succeeds_with_same_idempotency_key(db_session, fake_razorpay):
    demo_state.arm(2)  # fail the first 2 attempts, succeed on the 3rd
    result = checkout.propose_and_checkout(
        db_session, session_id="s6", llm_proposed_items=[{"product_id": 1, "qty": 1}], sleep_fn=lambda s: None
    )
    assert result.allowed is True
    assert result.checkout_url is not None
    assert fake_razorpay["create_order"] == 1  # only the successful attempt reaches the fake SDK

    retry_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "gateway_retry", AuditLog.session_id == "s6")
        .all()
    )
    assert len(retry_rows) == 2
    assert all(r.status == "retrying" for r in retry_rows)


def test_gateway_failure_exhausts_retries_and_reports_graceful_error(db_session, fake_razorpay):
    demo_state.arm(99)  # fail every attempt
    result = checkout.propose_and_checkout(
        db_session, session_id="s7", llm_proposed_items=[{"product_id": 1, "qty": 1}], sleep_fn=lambda s: None
    )
    assert result.allowed is True  # mandate allowed it; the gateway is what failed
    assert result.checkout_url is None
    assert "unavailable" in result.reason
    assert fake_razorpay["create_order"] == 0  # every attempt failed before reaching the fake SDK

    error_row = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "order_created", AuditLog.session_id == "s7")
        .one()
    )
    assert error_row.status == "error"


def test_missing_product_id_is_reported_gracefully_not_raised(db_session, fake_razorpay):
    result = checkout.propose_and_checkout(
        db_session, session_id="s9", llm_proposed_items=[{"qty": 1}]  # no product_id at all
    )
    assert result.allowed is False
    assert "missing product_id" in result.reason
    assert fake_razorpay["create_order"] == 0


def test_payment_link_failure_after_order_created_is_recorded_not_raised(db_session, monkeypatch, fake_razorpay):
    def failing_create_payment_link(amount_paise, description, reference_id):
        raise RuntimeError("simulated payment-link API failure")

    monkeypatch.setattr(razorpay_client, "create_payment_link", failing_create_payment_link)

    result = checkout.propose_and_checkout(
        db_session, session_id="s10", llm_proposed_items=[{"product_id": 1, "qty": 1}]
    )
    assert result.allowed is True
    assert result.checkout_url is None
    assert result.order_id is not None
    assert "payment link could not be generated" in result.reason

    # The order is NOT untracked: it has an IdempotencyKey row and a terminal audit row.
    assert db_session.query(IdempotencyKey).filter(IdempotencyKey.razorpay_order_id == result.order_id).count() == 1
    order_row = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "order_created", AuditLog.session_id == "s10")
        .one()
    )
    assert order_row.status == "error"
    assert order_row.razorpay_order_id == result.order_id


def test_unknown_product_id_is_reported_gracefully_not_raised(db_session, fake_razorpay):
    result = checkout.propose_and_checkout(
        db_session, session_id="s8", llm_proposed_items=[{"product_id": 99999, "qty": 1}]
    )
    assert result.allowed is False
    assert "does not exist" in result.reason
    assert fake_razorpay["create_order"] == 0
