from app import razorpay_client


def _mock_full_flow(monkeypatch):
    monkeypatch.setattr(razorpay_client, "create_customer", lambda name, email, contact: {"id": "cust_route"})
    monkeypatch.setattr(
        razorpay_client, "create_authorization_order",
        lambda amount_paise, customer_id, max_amount_paise, expire_at: {"id": "order_route_auth"},
    )
    monkeypatch.setattr(razorpay_client, "verify_checkout_signature", lambda *a: True)
    monkeypatch.setattr(
        razorpay_client, "fetch_payment",
        lambda payment_id: {"id": payment_id, "token_id": "tok_route", "card": {"last4": "4242", "network": "Visa"}},
    )
    monkeypatch.setattr(
        razorpay_client, "create_order",
        lambda amount_paise, currency, receipt: {"id": "order_route_charge", "amount": amount_paise, "currency": currency},
    )
    monkeypatch.setattr(razorpay_client, "charge_recurring", lambda **kwargs: {"id": "pay_route", "status": "captured"})


def test_status_route_defaults_to_none(app_client):
    resp = app_client.get("/autopay/status")
    assert resp.json()["status"] == "none"


def test_full_setup_confirm_charge_flow_via_routes(app_client, monkeypatch):
    _mock_full_flow(monkeypatch)

    setup = app_client.post(
        "/autopay/setup", json={"name": "Route Test", "email": "r@example.com", "contact": "9812345670"}
    ).json()
    assert setup["order_id"] == "order_route_auth"

    confirm = app_client.post(
        "/autopay/confirm",
        json={"razorpay_order_id": "order_route_auth", "razorpay_payment_id": "pay_route_auth", "razorpay_signature": "sig"},
    ).json()
    assert confirm["ok"] is True
    assert confirm["status"] == "active"

    status = app_client.get("/autopay/status").json()
    assert status["status"] == "active"
    assert status["card_last4"] == "4242"

    purchase = app_client.post("/demo/agent-autopay-purchase", json={"product_id": 1, "qty": 1}).json()
    assert purchase["allowed"] is True
    assert purchase["charged_directly"] is True
    assert purchase["payment_id"] == "pay_route"


def test_confirm_with_bad_signature_returns_ok_false(app_client, monkeypatch):
    _mock_full_flow(monkeypatch)
    monkeypatch.setattr(razorpay_client, "verify_checkout_signature", lambda *a: False)

    app_client.post("/autopay/setup", json={"name": "T", "email": "t@example.com", "contact": "9812345670"})
    resp = app_client.post(
        "/autopay/confirm",
        json={"razorpay_order_id": "order_route_auth", "razorpay_payment_id": "pay_x", "razorpay_signature": "bad"},
    )
    body = resp.json()
    assert body["ok"] is False
    assert "signature" in body["error"]


def test_agent_autopay_purchase_without_setup_is_refused(app_client):
    resp = app_client.post("/demo/agent-autopay-purchase", json={"product_id": 1, "qty": 1})
    body = resp.json()
    assert body["allowed"] is False
    assert "no active autopay token" in body["reason"]


def test_revoke_route(app_client, monkeypatch):
    _mock_full_flow(monkeypatch)
    app_client.post("/autopay/setup", json={"name": "T", "email": "t@example.com", "contact": "9812345670"})
    app_client.post(
        "/autopay/confirm",
        json={"razorpay_order_id": "order_route_auth", "razorpay_payment_id": "pay_x", "razorpay_signature": "sig"},
    )
    assert app_client.get("/autopay/status").json()["status"] == "active"

    app_client.post("/autopay/revoke")
    assert app_client.get("/autopay/status").json()["status"] == "revoked"
