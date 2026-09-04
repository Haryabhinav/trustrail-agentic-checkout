import pytest

from app import ap2, mcp


@pytest.fixture()
def fake_razorpay(monkeypatch):
    from app import razorpay_client

    def fake_create_order(amount_paise, currency, receipt):
        return {"id": "order_mcp_1", "amount": amount_paise, "currency": currency}

    def fake_create_payment_link(amount_paise, description, reference_id):
        return {"short_url": "https://rzp.io/l/mcp_test"}

    monkeypatch.setattr(razorpay_client, "create_order", fake_create_order)
    monkeypatch.setattr(razorpay_client, "create_payment_link", fake_create_payment_link)


def test_search_catalog_dispatch(db_session):
    result = mcp.dispatch(db_session, "search_catalog", {"query": "mouse"})
    assert result["products"][0]["name"] == "Wireless Mouse"


def test_lookup_catalog_dispatch(db_session):
    result = mcp.dispatch(db_session, "lookup_catalog", {"product_id": 1})
    assert result["products"][0]["price"]["amount"] == 799
    assert result["products"][0]["availability"]["available"] is True


def test_lookup_catalog_unknown_product_raises_rpc_error(db_session):
    with pytest.raises(mcp.RpcError) as exc_info:
        mcp.dispatch(db_session, "lookup_catalog", {"product_id": 99999})
    assert exc_info.value.code == mcp.ERR_INVALID_PARAMS


def test_unknown_method_raises_method_not_found(db_session):
    with pytest.raises(mcp.RpcError) as exc_info:
        mcp.dispatch(db_session, "delete_everything", {})
    assert exc_info.value.code == mcp.ERR_METHOD_NOT_FOUND


def test_create_checkout_dispatch_returns_ap2_cart_mandate(db_session):
    result = mcp.dispatch(
        db_session, "create_checkout", {"checkout": {"line_items": [{"product_id": 1, "qty": 1}]}}
    )
    assert result["checkout"]["status"] == "open"
    assert result["ap2"]["cart_mandate"]["contents"]["total"]["amount"]["value"] == 799


def test_create_checkout_over_mandate_returns_rpc_error(db_session):
    with pytest.raises(mcp.RpcError) as exc_info:
        mcp.dispatch(
            db_session, "create_checkout", {"checkout": {"line_items": [{"product_id": 2, "qty": 10}]}}
        )
    assert exc_info.value.code == mcp.ERR_CART_MANDATE


def test_get_checkout_dispatch(db_session):
    created = mcp.dispatch(
        db_session, "create_checkout", {"checkout": {"line_items": [{"product_id": 1, "qty": 1}]}}
    )
    cart_id = created["checkout"]["id"]

    result = mcp.dispatch(db_session, "get_checkout", {"checkout": {"id": cart_id}})
    assert result["checkout"]["id"] == cart_id
    assert result["checkout"]["status"] == "open"


def test_full_mcp_checkout_flow_end_to_end(db_session, fake_razorpay):
    created = mcp.dispatch(
        db_session, "create_checkout", {"checkout": {"line_items": [{"product_id": 1, "qty": 1}]}}
    )
    cart_id = created["checkout"]["id"]

    payment_mandate = {
        "mandate_id": "pm_e2e",
        "cart_reference": cart_id,
        "total": {"value": 799},
        "user_authorization": ap2.expected_user_authorization("pm_e2e", cart_id),
    }
    result = mcp.dispatch(
        db_session, "complete_checkout", {"checkout": {"id": cart_id, "payment_mandate": payment_mandate}}
    )
    assert result["checkout"]["status"] == "completed"
    assert result["checkout"]["checkout_url"] == "https://rzp.io/l/mcp_test"


def test_complete_checkout_invalid_mandate_returns_rpc_error(db_session, fake_razorpay):
    created = mcp.dispatch(
        db_session, "create_checkout", {"checkout": {"line_items": [{"product_id": 1, "qty": 1}]}}
    )
    cart_id = created["checkout"]["id"]

    bad_mandate = {"mandate_id": "pm_bad", "cart_reference": cart_id, "total": {"value": 1}, "user_authorization": "x"}
    with pytest.raises(mcp.RpcError) as exc_info:
        mcp.dispatch(db_session, "complete_checkout", {"checkout": {"id": cart_id, "payment_mandate": bad_mandate}})
    assert exc_info.value.code == mcp.ERR_PAYMENT_MANDATE
