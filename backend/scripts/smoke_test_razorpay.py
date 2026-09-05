"""Manual, human-in-the-loop smoke test for the real Razorpay test-mode integration.

This is NOT part of the automated pytest suite — it requires real RAZORPAY_KEY_ID /
RAZORPAY_KEY_SECRET env vars and a human to complete a test-mode checkout in a browser.
Run it once after you have real keys, to prove the money rails work end to end before
building the agent loop on top of them (Phase 1 of the build plan).

Usage:
    cd backend
    RAZORPAY_KEY_ID=... RAZORPAY_KEY_SECRET=... python scripts/smoke_test_razorpay.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import razorpay_client  # noqa: E402


def main():
    if not os.getenv("RAZORPAY_KEY_ID") or not os.getenv("RAZORPAY_KEY_SECRET"):
        print("Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (test mode) before running this script.")
        sys.exit(1)

    print("Creating a test-mode order for INR 10.00 ...")
    order = razorpay_client.create_order(amount_paise=1000, currency="INR", receipt="smoke-test-1")
    print(f"  order created: {order['id']}")

    print("Creating a payment link for that order ...")
    link = razorpay_client.create_payment_link(
        amount_paise=1000, description="PayPilot smoke test", reference_id="smoke-test-1"
    )
    print(f"  payment link: {link['short_url']}")
    print()
    print("Open the link above, pay with a Razorpay test card (e.g. 4111 1111 1111 1111,")
    print("any future expiry, any CVV), and confirm in the Razorpay Dashboard > Webhooks")
    print("logs (or your running backend's /audit endpoint) that a payment.captured event")
    print("arrived at POST /webhooks/razorpay and was signature-verified.")


if __name__ == "__main__":
    main()
