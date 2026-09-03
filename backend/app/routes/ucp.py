from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Product

router = APIRouter()


@router.get("/.well-known/ucp")
def ucp_manifest():
    return {
        "capabilities": ["discovery", "checkout"],
        "checkout": {"handler": "razorpay_checkout", "test_mode": True},
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
