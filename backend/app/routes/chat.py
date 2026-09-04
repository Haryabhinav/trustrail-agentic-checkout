import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import autopay
from app.agent.gemini_client import GeminiClient
from app.agent.loop import run_turn
from app.checkout import propose_and_autocharge, propose_and_checkout
from app.db import get_db

router = APIRouter()

# Lazily-constructed, reused across every /chat request in this process. GeminiClient.__init__
# builds a GenerativeModel from the (static) system prompt + tool schema — rebuilding that on
# every single request was pure repeated work for a value that never changes at runtime; only
# start_chat(history=...) needs to run per request, and it already does.
_gemini_client: GeminiClient | None = None


def _get_gemini_client() -> GeminiClient:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client


# Server-side session history, keyed by session_id. In-memory and process-local is a
# deliberate simplification for a single-process demo (see IMPLEMENTATION.md speed/space
# tradeoffs) — history is not round-tripped through the HTTP body because the Gemini SDK's
# chat history contains protobuf objects that don't serialize cleanly through Pydantic, and
# there is no product requirement here for multi-process or persisted chat history.
_SESSION_HISTORY: dict[str, list] = {}


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    checkout_url: str | None = None


def _make_propose_cart_handler(db: Session, session_id: str):
    def handler(items: list[dict]) -> dict:
        # If the buyer has already saved a card (via /autopay/setup + Checkout.js — see
        # app/autopay.py), the agent completes the ENTIRE purchase itself: no checkout link,
        # no further human interaction. Otherwise it falls back to the checkout-link flow.
        # Either way the same pricing + mandate gate runs first — autopay changes how an
        # allowed purchase is executed, never whether one is allowed.
        if autopay.is_active(db):
            result = propose_and_autocharge(db, session_id=session_id, llm_proposed_items=items)
        else:
            result = propose_and_checkout(db, session_id=session_id, llm_proposed_items=items)

        return {
            "allowed": result.allowed,
            "reason": result.reason,
            "canonical_total_inr": result.priced_cart.total_inr if result.priced_cart else None,
            "checkout_url": result.checkout_url,
            "order_id": result.order_id,
            "charged_directly": result.charged_directly,
            "payment_id": result.payment_id,
        }

    return handler


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    session_id = req.session_id or str(uuid.uuid4())
    history = _SESSION_HISTORY.get(session_id, [])

    try:
        client = _get_gemini_client()
        outcome = run_turn(
            db,
            client,
            history=history,
            user_message=req.message,
            propose_cart_handler=_make_propose_cart_handler(db, session_id),
        )
    except Exception as exc:  # noqa: BLE001 - a Gemini-side failure (rate limit, timeout,
        # transient 5xx) must degrade to a clear chat message, not a raw 500. This does not
        # touch money: propose_cart's own retry/audit path in checkout.py is unaffected —
        # this only guards the LLM round trip itself.
        return ChatResponse(
            session_id=session_id,
            reply=(
                "I'm having trouble reaching the shopping assistant right now "
                f"({exc.__class__.__name__}). Please try again in a moment."
            ),
            checkout_url=None,
        )

    _SESSION_HISTORY[session_id] = outcome["history"]

    return ChatResponse(
        session_id=session_id,
        reply=outcome["reply"],
        checkout_url=outcome["checkout_url"],
    )
