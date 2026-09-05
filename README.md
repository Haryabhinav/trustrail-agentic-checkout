# PayPilot

A deterministic checkout gateway that makes a Razorpay merchant natively transactable by AI
shopping agents — the LLM proposes carts, the server independently re-prices, mandate-checks,
and authorizes every purchase before any Razorpay API call is made.

## Prerequisites

- Docker + Docker Compose (recommended), **or** Python 3.11+ and Node 20+ for running locally
- A [Gemini API key](https://aistudio.google.com/apikey)
- A [Razorpay](https://razorpay.com) test-mode account (Settings → API Keys) for real checkout

## Setup

```
cp .env.example .env
```

Fill in `.env`:
- `GEMINI_API_KEY` — required for the chat agent
- `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` — required for real order/checkout creation
- `RAZORPAY_WEBHOOK_SECRET` — only needed if you're capturing `payment.captured` webhooks (requires a webhook registered against a publicly reachable URL, e.g. via a tunnel)
- `ALLOWED_ORIGINS` — comma-separated frontend origins allowed to call the API (defaults to `http://localhost:5173`). This app has no user login by design, so a wildcard here would let any website's JS trigger money-moving endpoints from a merchant's browser session — restrict it to real origins for anything beyond local use.
- `ENABLE_DEMO_ROUTES` — set to `false` to not mount `/demo/*` at all. Those endpoints exist purely to make the demo scenarios below repeatable on cue; they can move real money or flip shared process state with a single unauthenticated request, so a real deployment should disable them.
- `AP2_MOCK_SIGNING_SECRET` — set a real random value for anything beyond local demo use (see `.env.example` for why).

## Run with Docker

```
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

The catalog seeds itself on first boot.

## Run locally without Docker

```
# backend
cd backend
python -m venv .venv && source .venv/Scripts/activate   # .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

## Two ways to buy

- **Chat**: `POST /chat` — the embedded Gemini shopping agent.
- **UCP/AP2 (external agents)**: `GET /.well-known/ucp` for discovery, then JSON-RPC calls to
  `POST /mcp` (`search_catalog`, `create_checkout`, `complete_checkout`, ...) — Google's real
  Universal Commerce Protocol + Agent Payments Protocol shape, so any UCP-speaking agent can
  transact here without touching the chat UI at all.

Both paths terminate in the same server-side pricing/mandate/order pipeline — neither an
external caller nor the chat model can set a price or bypass the spend limit.

## Tests

```
cd backend
source .venv/Scripts/activate
python -m pytest -v
```

No external credentials required — the suite mocks the Razorpay SDK and the Gemini client.
