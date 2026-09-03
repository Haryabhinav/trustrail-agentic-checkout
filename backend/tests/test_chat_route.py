import pytest

from app.routes import chat as chat_route


class RaisingClient:
    """Stands in for GeminiClient to simulate a Gemini-side failure (rate limit, timeout,
    transient 5xx) without needing network access or a real key."""

    def __init__(self):
        raise RuntimeError("simulated 429 ResourceExhausted")


@pytest.fixture(autouse=True)
def _reset_gemini_client_singleton():
    # routes/chat.py caches one GeminiClient instance per process (see _get_gemini_client) —
    # reset it around this test so test ordering can never leave a cached client (real or a
    # prior monkeypatch's) sitting in module state.
    chat_route._gemini_client = None
    yield
    chat_route._gemini_client = None


def test_chat_degrades_gracefully_on_gemini_failure(app_client, monkeypatch):
    monkeypatch.setattr(chat_route, "GeminiClient", RaisingClient)

    resp = app_client.post("/chat", json={"message": "hello"})

    assert resp.status_code == 200  # never a raw 500
    body = resp.json()
    assert "trouble reaching" in body["reply"]
    assert body["checkout_url"] is None
    assert body["session_id"]  # a session id is still issued so the client can retry


def test_gemini_client_constructed_only_once_across_requests(app_client, monkeypatch):
    construct_count = {"n": 0}

    class FakeChat:
        history = []

    class FakeGeminiClient:
        """Succeeds on construction (unlike RaisingClient above), so _get_gemini_client's
        singleton cache actually gets populated and this test can prove it stays populated."""

        def __init__(self):
            construct_count["n"] += 1

        def start_chat(self, history=None):
            return FakeChat()

        def send_message(self, chat, message):
            return {"text": "ok", "function_calls": []}

        def send_function_results(self, chat, results):
            return {"text": "ok", "function_calls": []}

    monkeypatch.setattr(chat_route, "GeminiClient", FakeGeminiClient)

    app_client.post("/chat", json={"message": "first"})
    app_client.post("/chat", json={"message": "second"})
    app_client.post("/chat", json={"message": "third"})

    assert construct_count["n"] == 1  # reused across all three requests, not rebuilt each time
