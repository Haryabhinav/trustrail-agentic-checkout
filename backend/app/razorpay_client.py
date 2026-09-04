"""Thin Razorpay SDK wrapper. This module is the ONLY place in the codebase allowed to
call the Razorpay API. Nothing in app/agent/ imports this module — enforced by
tests/test_disposal_boundary.py, which asserts on the Gemini tool schema itself.
"""
import hashlib
import hmac

import razorpay
import requests

from app import config

_client: razorpay.Client | None = None


class _TimeoutSession(requests.Session):
    """Applies a default request timeout, since requests.Session has none and the razorpay
    SDK's own call sites don't pass one."""

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", config.UPSTREAM_REQUEST_TIMEOUT_SECONDS)
        return super().request(*args, **kwargs)


def get_client() -> razorpay.Client:
    global _client
    if _client is None:
        if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET:
            raise RuntimeError(
                "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set — cannot call Razorpay."
            )
        _client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET), session=_TimeoutSession())
    return _client


def create_order(amount_paise: int, currency: str, receipt: str) -> dict:
    """receipt should be the idempotency key."""
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


# --- Autopay (tokenized recurring charge) — see app/autopay.py ---

def create_customer(name: str, email: str, contact: str) -> dict:
    client = get_client()
    return client.customer.create({"name": name, "email": email, "contact": contact, "fail_existing": "0"})


def create_authorization_order(amount_paise: int, customer_id: str, max_amount_paise: int, expire_at: int) -> dict:
    """The order a human completes via Checkout.js to save their card as a token.
    token.max_amount is a Razorpay-enforced ceiling on any later silent charge."""
    client = get_client()
    return client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "customer_id": customer_id,
            "payment_capture": 1,
            "token": {"max_amount": max_amount_paise, "expire_at": expire_at, "frequency": "monthly"},
        }
    )


def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """hmac(order_id + '|' + payment_id, key_secret) — per Razorpay's Checkout.js docs."""
    if not signature:
        return False
    message = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(config.RAZORPAY_KEY_SECRET.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def fetch_payment(payment_id: str) -> dict:
    client = get_client()
    return client.payment.fetch(payment_id)


def charge_recurring(*, customer_id: str, token_id: str, order_id: str, amount_paise: int, email: str, contact: str) -> dict:
    """POST /v1/payments/create/recurring — the zero-human-interaction charge."""
    client = get_client()
    return client.payment.createRecurring(
        {
            "email": email,
            "contact": contact,
            "amount": amount_paise,
            "currency": "INR",
            "order_id": order_id,
            "customer_id": customer_id,
            "token": token_id,
            "recurring": "1",
        }
    )
