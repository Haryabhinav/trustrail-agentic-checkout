from app import ap2


def test_mcp_route_search_catalog(app_client):
    resp = app_client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "search_catalog", "params": {"query": "mouse"}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["products"][0]["name"] == "Wireless Mouse"


def test_mcp_route_unknown_method_returns_jsonrpc_error(app_client):
    resp = app_client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "nonexistent", "params": {}})
    assert resp.status_code == 200  # JSON-RPC errors travel in the body, not the HTTP status
    body = resp.json()
    assert body["error"]["code"] == -32601


def test_mcp_route_missing_method_returns_invalid_request(app_client):
    resp = app_client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "params": {}})
    assert resp.json()["error"]["code"] == -32600


def test_mcp_route_non_rpc_error_still_returns_jsonrpc_envelope_not_raw_500(app_client, monkeypatch):
    # A failure that ISN'T an mcp.RpcError (e.g. a DB/programming error inside a method
    # handler) used to propagate as a raw HTTP 500, breaking the JSON-RPC protocol contract
    # every other error path honors.
    from app import mcp as mcp_module

    def _boom(db, params):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr(mcp_module, "_method_search_catalog", _boom)
    monkeypatch.setitem(mcp_module._METHODS, "search_catalog", _boom)

    resp = app_client.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "search_catalog", "params": {"query": "x"}})
    assert resp.status_code == 200  # never a raw 500
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 5
    assert body["error"]["code"] == -32603


def test_mcp_route_malformed_json_returns_parse_error(app_client):
    resp = app_client.post("/mcp", content=b"{not valid json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32700


def test_mcp_route_full_checkout_flow(app_client, db_session, monkeypatch):
    from app import razorpay_client

    monkeypatch.setattr(
        razorpay_client, "create_order",
        lambda amount_paise, currency, receipt: {"id": "order_route_1", "amount": amount_paise, "currency": currency},
    )
    monkeypatch.setattr(
        razorpay_client, "create_payment_link",
        lambda amount_paise, description, reference_id: {"short_url": "https://rzp.io/l/route_test"},
    )

    created = app_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "create_checkout",
              "params": {"checkout": {"line_items": [{"product_id": 1, "qty": 1}]}}},
    ).json()
    cart_id = created["result"]["checkout"]["id"]
    assert created["result"]["ap2"]["cart_mandate"]["contents"]["total"]["amount"]["value"] == 799

    payment_mandate = {
        "mandate_id": "pm_route",
        "cart_reference": cart_id,
        "total": {"value": 799},
        "user_authorization": ap2.expected_user_authorization("pm_route", cart_id),
    }
    completed = app_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "complete_checkout",
              "params": {"checkout": {"id": cart_id, "payment_mandate": payment_mandate}}},
    ).json()
    assert completed["result"]["checkout"]["status"] == "completed"
    assert completed["result"]["checkout"]["checkout_url"] == "https://rzp.io/l/route_test"


def test_ucp_manifest_matches_real_spec_shape(app_client):
    resp = app_client.get("/.well-known/ucp")
    assert resp.status_code == 200
    body = resp.json()
    ucp = body["ucp"]
    assert ucp["services"]["dev.ucp.shopping"][0]["transport"] == "mcp"
    assert ucp["services"]["dev.ucp.shopping"][0]["endpoint"] == "/mcp"
    assert "dev.ucp.shopping.checkout" in ucp["capabilities"]
    assert "dev.ucp.shopping.ap2_mandate" in ucp["capabilities"]
    assert "com.razorpay.checkout" in ucp["payment_handlers"]
