import datetime

from sqlalchemy import Column, Integer, String, DateTime, Index

from app.db import Base


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    price_inr = Column(Integer, nullable=False)
    stock_qty = Column(Integer, nullable=False, default=0)
    description = Column(String, nullable=False, default="")


class Mandate(Base):
    __tablename__ = "mandate"

    id = Column(Integer, primary_key=True)  # single row, id=1
    max_spend_inr = Column(Integer, nullable=False)
    allowed_categories = Column(String, nullable=False)  # comma-separated
    spent_so_far_inr = Column(Integer, nullable=False, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    event_type = Column(String, nullable=False)
    # llm_proposal | mandate_check | order_created | payment_captured
    # | rejected_injection | price_mismatch_corrected | gateway_retry | webhook_received

    llm_rationale = Column(String, nullable=True)
    llm_said_json = Column(String, nullable=True)
    server_used_json = Column(String, nullable=True)
    canonical_price_inr = Column(Integer, nullable=True)
    mandate_check_result = Column(String, nullable=False, default="na")  # pass | fail | na
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="ok")  # ok | blocked | error | retrying | pending


Index("ix_audit_session_timestamp", AuditLog.session_id, AuditLog.timestamp)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String, primary_key=True)
    razorpay_order_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"

    razorpay_event_id = Column(String, primary_key=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class SavedPaymentToken(Base):
    """A tokenized card — see app/autopay.py. Single row (id=1), one buyer, no multi-tenant
    customer base."""
    __tablename__ = "saved_payment_tokens"

    id = Column(Integer, primary_key=True)  # single row, id=1
    razorpay_customer_id = Column(String, nullable=False)
    customer_email = Column(String, nullable=False)
    customer_contact = Column(String, nullable=False)
    token_id = Column(String, nullable=True)  # set once the authorization payment confirms
    card_last4 = Column(String, nullable=True)
    card_network = Column(String, nullable=True)
    status = Column(String, nullable=False, default="none")  # none | pending | active | revoked
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class CartMandateRecord(Base):
    """AP2 CartMandate: a price-locked cart, consumed once by complete_checkout — see
    app/ap2.py."""
    __tablename__ = "cart_mandates"

    id = Column(String, primary_key=True)  # "chk_" + uuid hex
    items_json = Column(String, nullable=False)  # raw [{product_id, qty}] the mandate covers
    total_inr = Column(Integer, nullable=False)  # locked price at issuance
    category = Column(String, nullable=False)
    merchant_authorization = Column(String, nullable=False)  # mock signature — see app/ap2.py
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False, default="open")  # open | completed | expired | failed
