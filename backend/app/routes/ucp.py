from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.models import Product

router = APIRouter()

UCP_SPEC_VERSION = "2026-01-15"


@router.get("/.well-known/ucp")
def ucp_manifest():
    """Matches Google's published UCP manifest format — see app/mcp.py (transport) and
    app/ap2.py (mandate flow)."""
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
        "catalog_url": "/catalog",  # plain REST mirror, for callers not speaking MCP
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
