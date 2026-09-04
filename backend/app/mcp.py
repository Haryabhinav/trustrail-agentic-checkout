"""MCP (Model Context Protocol) JSON-RPC 2.0 transport for UCP's shopping capabilities.

This is what `/.well-known/ucp` advertises as `services: [{transport: "mcp", endpoint: "/mcp"}]`
— an external AI buyer (or another agent framework) talks to this endpoint directly, with
zero involvement from this merchant's own chat agent (app/agent/). That's the literal
"enables AI-to-AI transactions" requirement: two completely independent code paths
(chat agent vs. external MCP caller) both terminate at the same disposal boundary
(app.checkout.propose_and_checkout), never at a second, weaker one.

Methods implemented, matching UCP's `dev.ucp.shopping` capability namespace:
  search_catalog, lookup_catalog, create_checkout, get_checkout, complete_checkout
"""
import json

from sqlalchemy.orm import Session

from app import ap2
from app.agent.tools import search_catalog as _search_catalog
from app.models import CartMandateRecord, Product


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# JSON-RPC 2.0 reserves -32000..-32099 for implementation-defined server errors.
ERR_INVALID_PARAMS = -32602
ERR_METHOD_NOT_FOUND = -32601
ERR_CART_MANDATE = -32001
ERR_PAYMENT_MANDATE = -32002


def _method_search_catalog(db: Session, params: dict) -> dict:
    query = params.get("query", "")
    return {"products": _search_catalog(db, query)}


def _method_lookup_catalog(db: Session, params: dict) -> dict:
    product_id = params.get("product_id")
    if product_id is None:
        raise RpcError(ERR_INVALID_PARAMS, "lookup_catalog requires product_id")
    product = db.query(Product).filter(Product.id == product_id).one_or_none()
    if product is None:
        raise RpcError(ERR_INVALID_PARAMS, f"no product with id {product_id}")
    return {
        "products": [
            {
                "id": product.id,
                "name": product.name,
                "category": product.category,
                "price": {"amount": product.price_inr, "currency": "INR"},
                "availability": {"available": product.stock_qty > 0, "stock_qty": product.stock_qty},
                "description": product.description,
            }
        ]
    }


def _method_create_checkout(db: Session, params: dict) -> dict:
    checkout = params.get("checkout") or {}
    line_items = checkout.get("line_items")
    if not line_items:
        raise RpcError(ERR_INVALID_PARAMS, "create_checkout requires checkout.line_items")

    try:
        cart_mandate = ap2.create_cart_mandate(db, line_items, session_id="ucp:create_checkout")
    except ap2.CartMandateError as exc:
        raise RpcError(ERR_CART_MANDATE, str(exc)) from exc

    return {
        "checkout": {"id": cart_mandate.id, "status": "open", "items": cart_mandate.items},
        **cart_mandate.to_ap2_dict(),
    }


def _method_get_checkout(db: Session, params: dict) -> dict:
    checkout_id = (params.get("checkout") or {}).get("id")
    if not checkout_id:
        raise RpcError(ERR_INVALID_PARAMS, "get_checkout requires checkout.id")

    try:
        record: CartMandateRecord = ap2.get_cart_mandate(db, checkout_id)
    except ap2.CartMandateError as exc:
        raise RpcError(ERR_CART_MANDATE, str(exc)) from exc

    return {
        "checkout": {
            "id": record.id,
            "status": record.status,
            "total": {"amount": record.total_inr, "currency": "INR"},
            "items": json.loads(record.items_json),
            "expires_at": record.expires_at.isoformat(),
        }
    }


def _method_complete_checkout(db: Session, params: dict) -> dict:
    checkout = params.get("checkout") or {}
    checkout_id = checkout.get("id")
    payment_mandate = checkout.get("payment_mandate")
    if not checkout_id or not payment_mandate:
        raise RpcError(ERR_INVALID_PARAMS, "complete_checkout requires checkout.id and checkout.payment_mandate")

    try:
        result = ap2.complete_checkout(db, cart_reference=checkout_id, payment_mandate=payment_mandate)
    except (ap2.CartMandateError, ap2.PaymentMandateError) as exc:
        raise RpcError(ERR_PAYMENT_MANDATE, str(exc)) from exc

    return {
        "checkout": {
            "id": checkout_id,
            "status": "completed" if result.checkout_url or result.order_id else "failed",
            "reason": result.reason,
            "order_id": result.order_id,
            "checkout_url": result.checkout_url,
        }
    }


_METHODS = {
    "search_catalog": _method_search_catalog,
    "lookup_catalog": _method_lookup_catalog,
    "create_checkout": _method_create_checkout,
    "get_checkout": _method_get_checkout,
    "complete_checkout": _method_complete_checkout,
}


def dispatch(db: Session, method: str, params: dict) -> dict:
    handler = _METHODS.get(method)
    if handler is None:
        raise RpcError(ERR_METHOD_NOT_FOUND, f"unknown method: {method}")
    return handler(db, params or {})
