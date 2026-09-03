from app import demo_state
from app.audit import log as audit_log


def test_ucp_manifest_declares_checkout_capability(app_client):
    resp = app_client.get("/.well-known/ucp")
    assert resp.status_code == 200
    body = resp.json()
    assert "checkout" in body["capabilities"]
    assert body["catalog_url"] == "/catalog"


def test_catalog_returns_seeded_products(app_client):
    resp = app_client.get("/catalog")
    assert resp.status_code == 200
    products = resp.json()
    assert len(products) == 10
    assert {"id", "name", "category", "price_inr", "stock_qty"} <= products[0].keys()


def test_audit_endpoint_returns_most_recent_first(app_client, db_session):
    audit_log(db_session, session_id="a", event_type="llm_proposal", status="ok")
    audit_log(db_session, session_id="a", event_type="mandate_check", status="blocked")

    resp = app_client.get("/audit")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0]["event_type"] == "mandate_check"
    assert rows[1]["event_type"] == "llm_proposal"


def test_health_check(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_demo_simulate_injection_is_rejected_deterministically(app_client, db_session):
    resp = app_client.post("/demo/simulate-injection", json={"product_id": 1, "qty": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is True
    assert body["canonical_total_inr"] == 799  # full price, no discount applied
    assert body["checkout_url"] is None  # fake_razorpay isn't mocked here; no real key in tests

    from app.models import AuditLog

    row = db_session.query(AuditLog).filter(AuditLog.event_type == "rejected_injection").one()
    assert row.status == "blocked"
    assert "discount_applied" in row.server_used_json


def test_demo_arms_and_reports_gateway_failure_state(app_client):
    resp = app_client.post("/demo/simulate-gateway-failure", json={"attempts": 3})
    assert resp.status_code == 200
    assert resp.json()["armed_failures"] == 3

    status = app_client.get("/demo/gateway-failure-status")
    assert status.json()["remaining_simulated_failures"] == 3

    demo_state.arm(0)  # reset for other tests
