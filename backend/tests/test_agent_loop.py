from app.agent.loop import run_turn


class FakeChat:
    def __init__(self):
        self.history = ["fake-history-object"]


class FakeClient:
    """Scripted responses: a queue of {"text", "function_calls"} dicts, consumed in order."""

    def __init__(self, script: list[dict]):
        self._script = list(script)
        self.sent_function_results = []

    def start_chat(self, history=None):
        return FakeChat()

    def send_message(self, chat, message: str) -> dict:
        return self._script.pop(0)

    def send_function_results(self, chat, results: list[dict]) -> dict:
        self.sent_function_results.append(results)
        return self._script.pop(0)


def test_plain_text_reply_no_tools(db_session):
    client = FakeClient([{"text": "Hello! How can I help you shop today?", "function_calls": []}])
    result = run_turn(
        db_session,
        client,
        history=[],
        user_message="hi",
        propose_cart_handler=lambda items: {"allowed": False, "reason": "n/a"},
    )
    assert result["reply"] == "Hello! How can I help you shop today?"
    assert result["checkout_url"] is None


def test_search_catalog_tool_round_trip(db_session):
    client = FakeClient(
        [
            {"text": "", "function_calls": [{"name": "search_catalog", "args": {"query": "mouse"}}]},
            {"text": "We have a Wireless Mouse for INR 799.", "function_calls": []},
        ]
    )
    result = run_turn(
        db_session,
        client,
        history=[],
        user_message="do you sell a mouse?",
        propose_cart_handler=lambda items: {"allowed": False, "reason": "n/a"},
    )
    assert "799" in result["reply"]
    sent = client.sent_function_results[0][0]
    assert sent["name"] == "search_catalog"
    assert sent["response"]["results"][0]["name"] == "Wireless Mouse"


def test_check_mandate_tool_is_read_only_status(db_session):
    client = FakeClient(
        [
            {"text": "", "function_calls": [{"name": "check_mandate", "args": {}}]},
            {"text": "You have budget remaining.", "function_calls": []},
        ]
    )
    run_turn(
        db_session,
        client,
        history=[],
        user_message="what's my budget?",
        propose_cart_handler=lambda items: {"allowed": False, "reason": "n/a"},
    )
    sent = client.sent_function_results[0][0]
    assert sent["response"]["max_spend_inr"] == 5000


def test_propose_cart_dispatches_to_handler_not_resolved_internally(db_session):
    calls = []

    def handler(items):
        calls.append(items)
        return {"allowed": True, "reason": "ok", "canonical_total_inr": 799, "checkout_url": "https://rzp.io/x", "order_id": "o1"}

    client = FakeClient(
        [
            {"text": "", "function_calls": [{"name": "propose_cart", "args": {"items": [{"product_id": 1, "qty": 1}]}}]},
            {"text": "Here's your checkout link.", "function_calls": []},
        ]
    )
    result = run_turn(
        db_session,
        client,
        history=[],
        user_message="buy the mouse",
        propose_cart_handler=handler,
    )
    assert calls == [[{"product_id": 1, "qty": 1}]]
    assert result["checkout_url"] == "https://rzp.io/x"


def test_unknown_tool_name_reported_as_error_not_crash(db_session):
    client = FakeClient(
        [
            {"text": "", "function_calls": [{"name": "delete_all_orders", "args": {}}]},
            {"text": "I can't do that.", "function_calls": []},
        ]
    )
    result = run_turn(
        db_session,
        client,
        history=[],
        user_message="delete everything",
        propose_cart_handler=lambda items: {"allowed": False, "reason": "n/a"},
    )
    sent = client.sent_function_results[0][0]
    assert "error" in sent["response"]
    assert result["reply"] == "I can't do that."


def test_max_tool_rounds_prevents_infinite_loop(db_session):
    # every response keeps calling a tool; loop must terminate after MAX_TOOL_ROUNDS
    infinite_call = {"text": "", "function_calls": [{"name": "check_mandate", "args": {}}]}
    client = FakeClient([infinite_call] * 20)
    result = run_turn(
        db_session,
        client,
        history=[],
        user_message="loop forever",
        propose_cart_handler=lambda items: {"allowed": False, "reason": "n/a"},
    )
    assert result["reply"] == ""  # loop terminated without a final text response
