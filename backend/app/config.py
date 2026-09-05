"""Environment configuration. No secrets have defaults except explicit demo-safe values."""
import os


def _list_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

MANDATE_MAX_SPEND_INR = int(os.getenv("MANDATE_MAX_SPEND_INR", "5000"))
MANDATE_ALLOWED_CATEGORIES = _list_env(
    "MANDATE_ALLOWED_CATEGORIES", "electronics,groceries,office-supplies"
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./paypilot.db")

# Prevents a hung upstream call from blocking a worker thread forever.
UPSTREAM_REQUEST_TIMEOUT_SECONDS = int(os.getenv("UPSTREAM_REQUEST_TIMEOUT_SECONDS", "15"))

DEMO_GATEWAY_FAILURE_ATTEMPTS = int(os.getenv("DEMO_GATEWAY_FAILURE_ATTEMPTS", "0"))

# No wildcard: a money-moving endpoint reachable from any origin is a CSRF-via-fetch() risk.
# Browser-enforced only — doesn't protect a direct server-to-server caller.
ALLOWED_ORIGINS = _list_env("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

# /demo/* can move real money or flip shared state with one unauthenticated request; exists
# to make demo scenarios repeatable on cue. Disable outside of an active demo.
ENABLE_DEMO_ROUTES = os.getenv("ENABLE_DEMO_ROUTES", "true").strip().lower() not in ("false", "0", "")

# UCP / AP2 (Universal Commerce Protocol / Agent Payments Protocol) — see app/ap2.py.
UCP_MERCHANT_NAME = os.getenv("UCP_MERCHANT_NAME", "PayPilot Demo Store")
AP2_MOCK_SIGNING_SECRET = os.getenv("AP2_MOCK_SIGNING_SECRET", "paypilot-demo-mock-signing-secret")
AP2_CART_MANDATE_TTL_SECONDS = int(os.getenv("AP2_CART_MANDATE_TTL_SECONDS", "300"))
