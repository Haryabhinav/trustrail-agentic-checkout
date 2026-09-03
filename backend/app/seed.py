from sqlalchemy.orm import Session

from app import config
from app.models import Mandate, Product

PRODUCTS = [
    dict(name="Wireless Mouse", category="electronics", price_inr=799, stock_qty=25,
         description="2.4GHz wireless mouse, ergonomic, USB receiver"),
    dict(name="Mechanical Keyboard", category="electronics", price_inr=2999, stock_qty=12,
         description="87-key hot-swappable mechanical keyboard"),
    dict(name="USB-C Hub", category="electronics", price_inr=1499, stock_qty=30,
         description="7-in-1 USB-C hub with HDMI and SD card reader"),
    dict(name="Noise Cancelling Earbuds", category="electronics", price_inr=3499, stock_qty=8,
         description="Active noise cancelling true wireless earbuds"),
    dict(name="Organic Basmati Rice 5kg", category="groceries", price_inr=649, stock_qty=50,
         description="Premium aged basmati rice, 5kg pack"),
    dict(name="Assorted Dry Fruits 1kg", category="groceries", price_inr=899, stock_qty=40,
         description="Mixed almonds, cashews, and raisins"),
    dict(name="Cold Pressed Olive Oil 1L", category="groceries", price_inr=549, stock_qty=35,
         description="Extra virgin cold pressed olive oil"),
    dict(name="A4 Copier Paper (500 sheets)", category="office-supplies", price_inr=349, stock_qty=100,
         description="75 GSM A4 size copier paper ream"),
    dict(name="Gel Pen Set (10 pcs)", category="office-supplies", price_inr=199, stock_qty=80,
         description="Smooth-write gel pens, assorted colors"),
    dict(name="Desk Organizer", category="office-supplies", price_inr=899, stock_qty=20,
         description="Multi-compartment wooden desk organizer"),
]


def seed_if_empty(db: Session) -> None:
    if db.query(Product).count() == 0:
        for p in PRODUCTS:
            db.add(Product(**p))

    if db.query(Mandate).filter(Mandate.id == 1).one_or_none() is None:
        db.add(
            Mandate(
                id=1,
                max_spend_inr=config.MANDATE_MAX_SPEND_INR,
                allowed_categories=",".join(config.MANDATE_ALLOWED_CATEGORIES),
                spent_so_far_inr=0,
            )
        )

    db.commit()
