"""Gemini tool schemas + read-only tool implementations. Nothing under app/agent/ imports
app.razorpay_client or app.checkout — propose_cart's actual disposal logic lives in
app.checkout, invoked via a callback from routes/chat.py. Enforced by
tests/test_disposal_boundary.py.
"""
from sqlalchemy.orm import Session

from app.models import Mandate, Product

TOOL_SCHEMAS = [
    {
        "name": "search_catalog",
        "description": "Search the product catalog by keyword. Read-only.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "search keywords"}},
            "required": ["query"],
        },
    },
    {
        "name": "propose_cart",
        "description": (
            "Propose a cart for the user. This does NOT purchase anything and does NOT set "
            "a price or discount — the backend independently recomputes the canonical price, "
            "checks it against the spend mandate, and returns the authoritative result "
            "(pass/fail, canonical total, and a checkout link if approved). Only pass "
            "product_id and qty — any price or discount field you include is ignored by the "
            "backend and logged as a rejected proposal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "qty": {"type": "integer"},
                        },
                        "required": ["product_id", "qty"],
                    },
                }
            },
            "required": ["items"],
        },
    },
    {
        "name": "check_mandate",
        "description": "Read-only status: remaining budget and allowed categories. Advisory only.",
        "parameters": {"type": "object", "properties": {}},
    },
]

# Checked by the disposal-boundary test: none of these may appear in a TOOL_SCHEMAS name.
FORBIDDEN_TOOL_NAME_FRAGMENTS = ["create_order", "capture", "charge", "pay", "refund", "transfer"]


def search_catalog(db: Session, query: str) -> list[dict]:
    q = f"%{query.lower()}%"
    products = (
        db.query(Product)
        .filter(Product.name.ilike(q) | Product.description.ilike(q) | Product.category.ilike(q))
        .all()
    )
    return [
        {
            "product_id": p.id,
            "name": p.name,
            "category": p.category,
            "price_inr": p.price_inr,
            "stock_qty": p.stock_qty,
            "description": p.description,
        }
        for p in products
    ]


def check_mandate_status(db: Session) -> dict:
    mandate = db.query(Mandate).filter(Mandate.id == 1).one_or_none()
    if mandate is None:
        return {"error": "mandate not configured"}
    return {
        "max_spend_inr": mandate.max_spend_inr,
        "spent_so_far_inr": mandate.spent_so_far_inr,
        "remaining_inr": mandate.max_spend_inr - mandate.spent_so_far_inr,
        "allowed_categories": [c.strip() for c in mandate.allowed_categories.split(",")],
    }
