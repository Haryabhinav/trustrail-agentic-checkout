"""Canonical cart pricing. Always recomputed server-side from the Product table.

Any price/discount field present in LLM-proposed cart items is discarded and never read —
this module's function signature doesn't even accept one, by design.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Product


class UnknownProductError(ValueError):
    pass


class InsufficientStockError(ValueError):
    pass


@dataclass
class PricedCart:
    items: list[dict]  # [{product_id, name, category, qty, unit_price_inr, line_total_inr}]
    total_inr: int
    category: str  # dominant/only category for this cart; used for the mandate check


def price_cart(db: Session, items: list[dict]) -> PricedCart:
    """items: [{"product_id": int, "qty": int}] — qty and id only. No price field is ever read."""
    if not items:
        raise ValueError("cart is empty")

    # Batch-fetch in one query instead of one round trip per line item.
    product_ids: set[int] = set()
    for raw in items:
        qty = int(raw.get("qty", 1))
        if qty <= 0:
            raise ValueError(f"invalid quantity for product {raw['product_id']}")
        product_ids.add(raw["product_id"])

    products_by_id = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}

    priced_items = []
    total = 0
    categories: set[str] = set()

    for raw in items:
        product_id = raw["product_id"]
        qty = int(raw.get("qty", 1))

        product = products_by_id.get(product_id)
        if product is None:
            raise UnknownProductError(f"product id {product_id} does not exist")
        if product.stock_qty < qty:
            raise InsufficientStockError(
                f"product '{product.name}' has only {product.stock_qty} in stock, requested {qty}"
            )

        line_total = product.price_inr * qty
        total += line_total
        categories.add(product.category)
        priced_items.append(
            {
                "product_id": product.id,
                "name": product.name,
                "category": product.category,
                "qty": qty,
                "unit_price_inr": product.price_inr,
                "line_total_inr": line_total,
            }
        )

    # Mixed-category carts are rejected at the mandate step, not here — see mandate.py.
    category = categories.pop() if len(categories) == 1 else "mixed"

    return PricedCart(items=priced_items, total_inr=total, category=category)
