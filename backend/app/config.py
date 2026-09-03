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

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trustrail.db")

DEMO_GATEWAY_FAILURE_ATTEMPTS = int(os.getenv("DEMO_GATEWAY_FAILURE_ATTEMPTS", "0"))
