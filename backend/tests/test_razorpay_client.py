import hashlib
import hmac

from app.razorpay_client import verify_webhook_signature

SECRET = "whsec_test_123"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_verifies():
    body = b'{"event": "payment.captured"}'
    assert verify_webhook_signature(body, _sign(body), SECRET) is True


def test_tampered_body_fails_verification():
    body = b'{"event": "payment.captured"}'
    signature = _sign(body)
    tampered_body = b'{"event": "payment.captured", "amount": 999999}'
    assert verify_webhook_signature(tampered_body, signature, SECRET) is False


def test_wrong_secret_fails_verification():
    body = b'{"event": "payment.captured"}'
    assert verify_webhook_signature(body, _sign(body, "wrong_secret"), SECRET) is False


def test_missing_signature_header_fails():
    body = b'{"event": "payment.captured"}'
    assert verify_webhook_signature(body, "", SECRET) is False


def test_missing_secret_fails_closed():
    body = b'{"event": "payment.captured"}'
    assert verify_webhook_signature(body, _sign(body), "") is False
