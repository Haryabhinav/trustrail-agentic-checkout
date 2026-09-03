"""Tool-use conversation loop. Depends only on the normalized client interface
(send_message / send_function_results returning {"text", "function_calls"}) — never on
google-generativeai's SDK types directly, and never on app.checkout / app.razorpay_client.

propose_cart is dispatched to a caller-supplied callback (propose_cart_handler), not resolved
inside this package — that is the structural half of the disposal-boundary guarantee.
See tests/test_disposal_boundary.py.
"""
from typing import Callable, Protocol

from sqlalchemy.orm import Session

from app.agent.tools import check_mandate_status, search_catalog

MAX_TOOL_ROUNDS = 5


class ChatClient(Protocol):
    def start_chat(self, history: list | None = None): ...
    def send_message(self, chat, message: str) -> dict: ...
    def send_function_results(self, chat, results: list[dict]) -> dict:  ...


def run_turn(
    db: Session,
    client: ChatClient,
    *,
    history: list,
    user_message: str,
    propose_cart_handler: Callable[[list[dict]], dict],
) -> dict:
    """Returns {"reply": str, "history": updated history, "checkout_url": str | None}."""
    chat = client.start_chat(history=history)
    result = client.send_message(chat, user_message)

    checkout_url = None

    for _ in range(MAX_TOOL_ROUNDS):
        if not result["function_calls"]:
            break

        tool_results = []
        for call in result["function_calls"]:
            name = call["name"]
            args = call["args"]

            if name == "search_catalog":
                response = {"results": search_catalog(db, args.get("query", ""))}
            elif name == "check_mandate":
                response = check_mandate_status(db)
            elif name == "propose_cart":
                outcome = propose_cart_handler(args.get("items", []))
                if outcome.get("checkout_url"):
                    checkout_url = outcome["checkout_url"]
                response = outcome
            else:
                response = {"error": f"unknown tool {name}"}

            tool_results.append({"name": name, "response": response})

        result = client.send_function_results(chat, tool_results)

    return {"reply": result["text"], "history": getattr(chat, "history", history), "checkout_url": checkout_url}
