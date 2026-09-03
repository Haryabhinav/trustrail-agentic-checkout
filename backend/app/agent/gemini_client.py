"""Real Gemini SDK adapter. Isolated in its own module so app/agent/loop.py's orchestration
logic can be unit-tested with a fake client and zero network/SDK dependency.

Exposes a small normalized interface (send_message / send_function_results, returning plain
dicts) so loop.py never touches google-generativeai's protobuf types directly.
"""
import google.generativeai as genai

from app import config
from app.agent.system_prompt import SYSTEM_PROMPT
from app.agent.tools import TOOL_SCHEMAS

_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set — cannot call Gemini.")
        genai.configure(api_key=config.GEMINI_API_KEY)
        _configured = True


def _to_plain(value):
    """Recursively convert protobuf MapComposite/RepeatedComposite (what `part.function_call.args`
    actually contains for nested fields, e.g. propose_cart's `items` list) into plain
    dict/list/scalar so json.dumps in app/audit.py doesn't blow up on a real tool call."""
    if hasattr(value, "items"):
        return {k: _to_plain(v) for k, v in value.items()}
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        return [_to_plain(v) for v in value]
    return value


def _normalize(response) -> dict:
    text_parts = []
    function_calls = []
    for part in response.candidates[0].content.parts:
        if getattr(part, "function_call", None) and part.function_call.name:
            function_calls.append(
                {"name": part.function_call.name, "args": _to_plain(part.function_call.args)}
            )
        elif getattr(part, "text", None):
            text_parts.append(part.text)
    return {"text": "\n".join(text_parts).strip(), "function_calls": function_calls}


class GeminiClient:
    """Chat-session wrapper. One instance of `chat` per HTTP /chat request in this app.
    Session history itself is kept process-local and in-memory by the caller
    (routes/chat.py's _SESSION_HISTORY dict, keyed by session_id) — a deliberate demo-scope
    simplification, not round-tripped through the HTTP request/response body."""

    def __init__(self):
        _ensure_configured()
        self._model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            tools=[{"function_declarations": TOOL_SCHEMAS}],
        )

    def start_chat(self, history: list | None = None):
        return self._model.start_chat(history=history or [])

    def send_message(self, chat, message: str) -> dict:
        return _normalize(chat.send_message(message))

    def send_function_results(self, chat, results: list[dict]) -> dict:
        """results: [{"name": str, "response": dict}]"""
        parts = [
            genai.protos.Part(
                function_response=genai.protos.FunctionResponse(name=r["name"], response=r["response"])
            )
            for r in results
        ]
        return _normalize(chat.send_message(genai.protos.Content(parts=parts)))
