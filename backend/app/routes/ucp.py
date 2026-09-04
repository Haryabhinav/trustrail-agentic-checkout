from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.models import Product

router = APIRouter()

UCP_SPEC_VERSION = "2026-01-15"  # matches Google's published UCP spec version this shape targets


@router.get("/.well-known/ucp")
def ucp_manifest():
    """Shaped to match Google's real, published UCP manifest format (spec version
    2026-01-15) — not an invented approximation. See app/mcp.py for the JSON-RPC transport
    this advertises, and app/ap2.py for the AP2 mandate flow behind `checkout`.
    """
    return {
        "ucp": {
            "version": UCP_SPEC_VERSION,
            "services": {
                "dev.ucp.shopping": [
                    {"version": UCP_SPEC_VERSION, "transport": "mcp", "endpoint": "/mcp"}
                ]
            },
            "capabilities": {
                "dev.ucp.shopping.catalog.search": [{"version": UCP_SPEC_VERSION}],
                "dev.ucp.shopping.catalog.lookup": [{"version": UCP_SPEC_VERSION}],
                "dev.ucp.shopping.checkout": [{"version": UCP_SPEC_VERSION}],
                "dev.ucp.shopping.ap2_mandate": [{"version": UCP_SPEC_VERSION}],
            },
            "payment_handlers": {
                "com.razorpay.checkout": [
                    {"id": "razorpay_test_mode", "version": UCP_SPEC_VERSION, "available_instruments": [{"type": "card"}]}
                ]
            },
        },
        # Kept alongside the spec-conformant `ucp` block for convenience — not part of UCP
        # itself, just a plain REST mirror of the catalog for anything that isn't speaking MCP.
        "catalog_url": "/catalog",
    }


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price_inr": p.price_inr,
            "stock_qty": p.stock_qty,
            "description": p.description,
        }
        for p in products
    ]
