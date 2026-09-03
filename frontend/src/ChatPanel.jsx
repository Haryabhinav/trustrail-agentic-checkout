import { useState, useRef, useEffect } from "react";

export default function ChatPanel() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hi! Ask me about the catalog, or ask me to put something in your cart." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function runInjectionDemo() {
    // Calls the same real disposal-boundary code (app.checkout.propose_and_checkout) that
    // routes/chat.py uses, with a synthetic hallucinated discount field — deterministic and
    // repeatable, unlike hoping the live model attempts a jailbreak in the chat itself
    // (Gemini correctly declines that at the conversational layer, which is good behavior
    // but not something a live demo should depend on).
    setMessages((m) => [
      ...m,
      { role: "user", text: "[demo] simulate a jailbroken tool call: propose_cart with discount: '100%'" },
    ]);
    setLoading(true);
    try {
      const res = await fetch("/demo/simulate-injection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`server returned ${res.status}`);
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: `Backend response: ${data.reason}. Canonical total charged: ₹${data.canonical_total_inr} (discount was ignored).`,
          checkoutUrl: data.checkout_url,
        },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `Something went wrong talking to the backend: ${err.message}`, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function send(text) {
    if (!text.trim() || loading) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      if (!res.ok) throw new Error(`server returned ${res.status}`);
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: data.reply, checkoutUrl: data.checkout_url },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `Something went wrong talking to the backend: ${err.message}`, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col rounded-lg border border-slate-800 bg-slate-900/50 overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between">
        <h2 className="font-medium text-sm text-slate-300">Shopping assistant</h2>
        <button
          onClick={runInjectionDemo}
          className="text-xs px-2 py-1 rounded bg-red-900/40 border border-red-700 text-red-300 hover:bg-red-900/70"
        >
          Run injection demo
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-indigo-600 text-white"
                  : m.error
                  ? "bg-red-950 border border-red-800 text-red-200"
                  : "bg-slate-800 text-slate-100"
              }`}
            >
              {m.text}
              {m.checkoutUrl && (
                <a
                  href={m.checkoutUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 block text-center rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium py-1.5"
                >
                  Complete checkout →
                </a>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="text-xs text-slate-500">thinking…</div>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-slate-800 p-3 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. do you have a wireless mouse?"
          className="flex-1 rounded bg-slate-800 border border-slate-700 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-4 py-2 text-sm font-medium"
        >
          Send
        </button>
      </form>
    </div>
  );
}
