# TrustRail

A deterministic checkout gateway that makes a Razorpay merchant natively transactable by AI
shopping agents. Built for the **Razorpay AI Buildathon 2026 — Track 01: AI Growth &
Agentic Commerce**.

> **The LLM proposes. The server disposes.** Nothing the model says is ever trusted as a
> price, discount, quantity confirmation, or payment authorization. See
> [`IMPLEMENTATION.md`](./IMPLEMENTATION.md) for the full architecture rationale and
> [`TRUSTRAIL_BUILD_PROMPT.md`](./TRUSTRAIL_BUILD_PROMPT.md) for the original spec.

## Architecture

```
Browser (React)                     FastAPI backend (single process)
 ChatPanel ───POST /chat──────►  routes/chat.py ──► agent/loop.py ──► Gemini (tool-use)
 AuditDashboard ──GET /audit──►  routes/audit.py         │  search_catalog / propose_cart /
                                                          │  check_mandate — all read-only
                                        ┌── DISPOSAL BOUNDARY (no LLM code past here) ──┐
                                        │ pricing.py · mandate.py · audit.py            │
                                        │ checkout.py (idempotent order + retry ladder) │
                                        │ razorpay_client.py                            │
                                        └────────────────────────────────────────────────┘
                                                          │
 Razorpay ◄──webhooks/razorpay (HMAC verified)──  routes/webhooks.py
 AI buyers ◄──GET /.well-known/ucp, GET /catalog── routes/ucp.py
```

Every `propose_cart` tool call is intercepted server-side: price is recomputed from the
`Product` table (never from the model), checked against the deterministic spend/category
mandate, logged to `AuditLog` unconditionally (pass or fail), and only then — if allowed —
turned into a Razorpay order with an idempotency key derived from `(session_id, cart)`.

## Repo layout

```
backend/
  app/
    main.py, config.py, db.py, models.py
    mandate.py       — pure deterministic spend/category gate
    pricing.py        — server-side cart repricing from the Product table
    checkout.py        — the disposal boundary: pricing → mandate → audit → order → retry
    razorpay_client.py  — the ONLY module allowed to call the Razorpay API
    audit.py, demo_state.py, seed.py
    agent/              — Gemini tool schemas + orchestration loop (never imports checkout/razorpay_client)
    routes/              — chat, webhooks, ucp/catalog, audit, demo
  tests/                  — 61 automated tests, no external keys required
  scripts/smoke_test_razorpay.py — manual live smoke test (needs real Razorpay keys)
frontend/
  src/ChatPanel.jsx, AuditDashboard.jsx, App.jsx
docker-compose.yml
```

## Setup

### 1. Environment

```
cp .env.example .env
# fill in GEMINI_API_KEY (required for the chat agent)
# fill in RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET / RAZORPAY_WEBHOOK_SECRET (required for real checkout)
```

Razorpay test-mode keys come from your own Razorpay Dashboard (Settings → API Keys) after a
free signup — there is no way to obtain someone else's keys, and this app will refuse to call
Razorpay without them (it fails loudly, not silently, per `razorpay_client.get_client()`).

For `RAZORPAY_WEBHOOK_SECRET`, you need a webhook registered pointing at a publicly reachable
URL for `POST /webhooks/razorpay` (a tunnel like `cloudflared tunnel --url http://localhost:8000`
or `ngrok http 8000` works for local dev). You can register it either in the Dashboard
(Settings → Webhooks → Add New Webhook, subscribe to `payment.captured`) or via the API:

```
curl -u $RAZORPAY_KEY_ID:$RAZORPAY_KEY_SECRET https://api.razorpay.com/v1/webhooks \
  -X POST -H "Content-Type: application/json" \
  -d '{"url": "https://<your-tunnel-url>/webhooks/razorpay", "secret": "<pick-a-secret>", "events": {"payment.captured": true}}'
```

Whatever `secret` you choose there is what goes in `RAZORPAY_WEBHOOK_SECRET`.

### 2. Run with Docker (recommended)

```
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

The backend seeds its SQLite catalog on first boot if empty (`app/seed.py`).

### 3. Run locally without Docker

```
# backend
cd backend
python -m venv .venv && source .venv/Scripts/activate   # or .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

## Running the automated test suite

```
cd backend
source .venv/Scripts/activate
python -m pytest -v
```

61 tests, all deterministic — no Gemini or Razorpay credentials required. They cover:
`mandate.py` (pure gate logic, boundary conditions), `pricing.py` (canonical repricing,
hallucinated-price rejection, stock/unknown-product errors), `checkout.py` (the full
disposal-boundary pipeline: happy path, mandate rejection, injection rejection, idempotent
replay, gateway retry-then-succeed, retry exhaustion, payment-link failure after order
creation, receipt/reference-id length truncation), `razorpay_client.py` (webhook HMAC
verification), `routes/webhooks.py` (signature rejection, replay dedup, spend accounting,
missing-event-id rejection), `routes/chat.py` (graceful degradation on a Gemini-side
failure), `agent/loop.py` (tool dispatch against a fake Gemini client),
`agent/gemini_client.py` (protobuf-to-plain-Python conversion of tool-call args), and
`tests/test_disposal_boundary.py` (a structural, AST-based proof that no module under
`app/agent/` imports `app.checkout` or `app.razorpay_client`, plus a check that the Gemini
tool schema exposes no money-moving function name).

**This has all also been verified live**, not just against mocks: real order + payment link
creation against a real Razorpay test-mode account (`scripts/smoke_test_razorpay.py`), and
the full chat → `search_catalog` → `propose_cart` → mandate check → real Razorpay order →
checkout link round trip against the real Gemini API. That live run caught one real bug
(Razorpay's `receipt` field rejects a full 64-char sha256 idempotency key — now truncated to
40 chars for Razorpay-facing calls while the full key stays canonical everywhere else) and
one design gap (a Gemini-side failure, e.g. hitting the free-tier rate limit, was surfacing
as a raw 500 instead of a graceful chat error) — both fixed and covered by regression tests.

Once you have real Razorpay keys:

```
cd backend
RAZORPAY_KEY_ID=... RAZORPAY_KEY_SECRET=... python scripts/smoke_test_razorpay.py
```

This creates a real test-mode order + payment link and walks you through completing it
manually to confirm the webhook lands with a valid signature.

## Demo script (read verbatim)

Have the app running (`docker compose up`) with both `GEMINI_API_KEY` and the three
`RAZORPAY_*` keys set, and the browser open on http://localhost:5173 with the Audit
Dashboard visible on the right.

### Scenario 1 — Happy path purchase

1. In the chat panel, type: *"Do you have a wireless mouse?"* — the model calls
   `search_catalog`, and you'll see the tool round-trip is read-only.
2. Type: *"Add it to my cart and check out."* — the model calls `propose_cart`. Watch the
   Audit Dashboard: a `mandate_check` row appears (`pass`), followed by an `order_created`
   row that flips from `pending` to `ok`.
3. Click **Complete checkout →** in the chat bubble, pay with a Razorpay test card
   (`4111 1111 1111 1111`, any future expiry, any CVV).
4. A `payment_captured` audit row appears once the webhook lands — signature-verified, spend
   counter updated.

### Scenario 2 — Prompt injection blocked

1. Click **Run injection demo** in the chat panel. This calls `POST /demo/simulate-injection`,
   which runs a cart with a hallucinated `discount: "100%"` field through the *exact same*
   `app.checkout.propose_and_checkout` code path `routes/chat.py` uses — deterministic and
   repeatable, rather than depending on the live model choosing to attempt a jailbreak in
   conversation (we tried this live against Gemini: it correctly declines the discount at the
   conversational layer every time, which is good AI-judgment behavior but not something a
   live demo should gamble on being reproducible in front of judges).
2. Point at the Audit Dashboard: a `rejected_injection` row appears in red, showing
   `llm_said` (the discount that was attempted) side-by-side with `server_used`
   (`discount_applied: 0`) — the checkout link that comes back is still the full,
   undiscounted price. If you want to also show the model declining in natural conversation,
   just ask it directly to apply a discount — it will refuse in-chat *and* the server-side
   block still exists underneath as defense in depth.

### Scenario 3 — Gateway failure recovered

1. Click **Simulate gateway failure (2 attempts)** — this arms `demo_state` to make the next
   two `create_order` calls raise a simulated Razorpay 502.
2. Ask the assistant to buy something. Watch the Audit Dashboard show two `gateway_retry`
   rows (amber, `retrying`) with the *same* idempotency key, followed by a successful
   `order_created` row — exactly one order was created despite two failures. (We compress the
   real 0s/1m/2m/5m backoff ladder to 0s/1s/2s/3s for the live demo — labeled here on
   screen, not hidden.)
3. To show the exhausted-retry path instead, arm more failures than there are retry attempts
   (e.g. `{"attempts": 10}` via `POST /demo/simulate-gateway-failure`) — the chat gets a
   clear, graceful error instead of a link, and the Audit Dashboard shows a final `error` row
   instead of a crash.

## What's implemented vs. what needs your keys to fully verify

| Area | Status |
|---|---|
| Mandate gate, pricing, audit trail, idempotency, webhook HMAC verification, injection rejection, retry/backoff | ✅ Implemented, 61 automated tests, **and verified live** |
| Disposal-boundary guarantee (LLM can't reach Razorpay) | ✅ Implemented and structurally tested (AST import check + tool-schema check) |
| UCP discoverability (`/.well-known/ucp`, `/catalog`) | ✅ Implemented and tested |
| Chat agent (Gemini tool-use loop) | ✅ **Verified live** against a real `GEMINI_API_KEY` — `search_catalog` and `propose_cart` round trips both confirmed working end to end |
| Real Razorpay order/payment-link round trip | ✅ **Verified live** against a real Razorpay test-mode account — real orders and payment links created for all three demo scenarios (happy path, injection block, gateway-retry) |
| Webhook `payment.captured` → spend accounting | ✅ **Verified live**: a real webhook was registered against this Razorpay account (via the Webhooks API) pointing at a real public tunnel (Cloudflare Tunnel) in front of the actual running backend. A payload matching Razorpay's documented shape, signed with the real secret Razorpay returned on registration, was sent through that live public path — signature acceptance, HMAC-tamper rejection (400), replay dedup (`duplicate, ignored`, spend incremented exactly once), and the `payment_captured` audit row were all confirmed. The one thing not exercised is a payment completed through Razorpay's own hosted checkout UI (which needs a browser and a human) — everything downstream of Razorpay's delivery is proven. |
| Mandate double-spend race under true concurrency | ⚠️ Known, named limitation — see `IMPLEMENTATION.md` §5. Not exploitable in the single-process demo (SQLite single-writer), would need a reserved-spend design for production. |

**Demo-day note on Gemini quota:** live testing was done against a **free-tier** Gemini API
key, capped at 5 requests/minute for `gemini-2.5-flash`. Each chat turn that calls a tool
costs 2+ requests (the initial call plus one per tool round), so it's easy to hit the limit
during rehearsal. If you're presenting live: either upgrade to a paid tier beforehand, or
rehearse the three scenarios with pauses between them and don't chain retries — a hit quota
now degrades gracefully (a clear "please try again in a moment" chat message, confirmed live)
rather than crashing, but it will visibly interrupt a rapid-fire demo.
