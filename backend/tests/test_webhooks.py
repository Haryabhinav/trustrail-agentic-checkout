import hashlib
import hmac
import json

from app.models import AuditLog, Mandate, ProcessedWebhookEvent

SECRET = "test_webhook_secret"


def _payload(event_id="evt_1", amount_paise=79900, order_id="order_1", payment_id="pay_1"):
    return {
        "id": event_id,
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": payment_id, "order_id": order_id, "amount": amount_paise}
            }
        },
    }


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_valid_webhook_increments_spend_and_logs_audit(app_client, db_session):
    body = json.dumps(_payload()).encode()
    resp = app_client.post(
        "/webhooks/razorpay", content=body, headers={"x-razorpay-signature": _sign(body)}
    )
    assert resp.status_code == 200

    mandate = db_session.query(Mandate).filter(Mandate.id == 1).one()
    assert mandate.spent_so_far_inr == 799

    row = db_session.query(AuditLog).filter(AuditLog.event_type == "payment_captured").one()
    assert row.razorpay_order_id == "order_1"
    assert row.razorpay_payment_id == "pay_1"


def test_invalid_signature_rejected_with_400(app_client, db_session):
    body = json.dumps(_payload()).encode()
    resp = app_client.post(
        "/webhooks/razorpay", content=body, headers={"x-razorpay-signature": "not_a_real_signature"}
    )
    assert resp.status_code == 400

    mandate = db_session.query(Mandate).filter(Mandate.id == 1).one()
    assert mandate.spent_so_far_inr == 0


def test_missing_event_id_is_rejected_not_silently_collapsed(app_client, db_session):
    payload = _payload()
    del payload["id"]  # no top-level id and no x-razorpay-event-id header either
    body = json.dumps(payload).encode()
    resp = app_client.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": _sign(body)})
    assert resp.status_code == 400

    mandate = db_session.query(Mandate).filter(Mandate.id == 1).one()
    assert mandate.spent_so_far_inr == 0


def test_malformed_json_body_rejected_with_400(app_client, db_session):
    body = b"{not valid json"
    resp = app_client.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": _sign(body)})
    assert resp.status_code == 400
    assert "not valid JSON" in resp.json()["detail"]


def test_malformed_amount_rejected_with_400_not_500(app_client, db_session):
    payload = _payload(event_id="evt_bad_amount")
    payload["payload"]["payment"]["entity"]["amount"] = "not-a-number"
    body = json.dumps(payload).encode()
    resp = app_client.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": _sign(body)})
    assert resp.status_code == 400

    mandate = db_session.query(Mandate).filter(Mandate.id == 1).one()
    assert mandate.spent_so_far_inr == 0


def test_failed_request_does_not_leave_a_dangling_dedupe_marker(app_client, db_session):
    # Regression test for the webhook-atomicity fix: the dedupe row used to be committed
    # immediately, before the spend increment — so a failure partway through could
    # permanently mark an event "processed" while the spend update was lost. It's now staged
    # (not committed) until the single commit at the end of a successful request. Prove this
    # black-box: a request that fails before reaching that commit must not have poisoned the
    # dedupe key — a subsequent valid request with the SAME event id must still go through.
    event_id = "evt_atomic_test"

    bad_payload = _payload(event_id=event_id)
    bad_payload["payload"]["payment"]["entity"]["amount"] = "not-a-number"
    bad_body = json.dumps(bad_payload).encode()
    bad_resp = app_client.post("/webhooks/razorpay", content=bad_body, headers={"x-razorpay-signature": _sign(bad_body)})
    assert bad_resp.status_code == 400
    db_session.rollback()  # what a real request-scoped session would do on the way out via get_db()

    good_body = json.dumps(_payload(event_id=event_id)).encode()
    good_resp = app_client.post("/webhooks/razorpay", content=good_body, headers={"x-razorpay-signature": _sign(good_body)})
    assert good_resp.status_code == 200
    assert good_resp.json()["status"] == "ok"  # not "duplicate, ignored"

    mandate = db_session.query(Mandate).filter(Mandate.id == 1).one()
    assert mandate.spent_so_far_inr == 799


def test_replayed_webhook_does_not_double_count_spend(app_client, db_session):
    body = json.dumps(_payload(event_id="evt_dup")).encode()
    signature = _sign(body)

    r1 = app_client.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": signature})
    r2 = app_client.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": signature})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate, ignored"

    mandate = db_session.query(Mandate).filter(Mandate.id == 1).one()
    assert mandate.spent_so_far_inr == 799  # not 1598

    assert db_session.query(ProcessedWebhookEvent).count() == 1
