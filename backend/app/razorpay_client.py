"""Thin Razorpay SDK wrapper. This module is the ONLY place in the codebase allowed to
call the Razorpay API. Nothing in app/agent/ imports this module — enforced by
tests/test_disposal_boundary.py, which asserts on the Gemini tool schema itself.
"""
import hashlib
import hmac

import razorpay

from app import config

_client: razorpay.Client | None = None


def get_client() -> razorpay.Client:
    global _client
    if _client is None:
        if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET:
            raise RuntimeError(
                "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set — cannot call Razorpay."
            )
        _client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
    return _client


def create_order(amount_paise: int, currency: str, receipt: str) -> dict:
    """receipt should be the idempotency key — Razorpay dedupes orders by receipt per docs
    recommendation, and we additionally dedupe ourselves via IdempotencyKey table."""
    client = get_client()
    return client.order.create(
        {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "payment_capture": 1,
        }
    )


def create_payment_link(amount_paise: int, description: str, reference_id: str) -> dict:
    client = get_client()
    return client.payment_link.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "reference_id": reference_id,
        }
    )


def verify_webhook_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
