import { useState, useRef, useEffect } from "react";
import { Sparkles, User, MoreVertical, RotateCcw, AlertTriangle, Check, Copy, ArrowRight, Send, Loader2, Plus } from "lucide-react";

const SUGGESTIONS = [
  "Do you have a wireless mouse?",
  "What's in the office-supplies category?",
  "Add a mechanical keyboard to my cart",
  "What's my remaining budget?",
];

function TypingDots() {
  return (
    <div className="flex items-center gap-2 px-1 text-xs text-slate-500">
      <span className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-slate-500 [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-slate-500 [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-slate-500 [animation-delay:300ms]" />
      </span>
      thinking
    </div>
  );
}

function AssistantAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-rzp to-blue-700 text-white shadow-sm ring-1 ring-white/10">
      <Sparkles className="h-3.5 w-3.5" strokeWidth={2} />
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-700 text-slate-200 shadow-sm ring-1 ring-white/10">
      <User className="h-3.5 w-3.5" strokeWidth={1.8} />
    </div>
  );
}

function HeaderMenu({ sessionId, hasMessages, onNewChat, onRunInjection }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`flex h-7 w-7 items-center justify-center rounded-lg border transition ${
          open ? "border-white/[0.15] bg-white/[0.06] text-slate-200" : "border-white/[0.08] bg-white/[0.02] text-slate-400 hover:border-white/[0.15] hover:text-slate-200"
        }`}
        title="More options"
      >
        <MoreVertical className="h-4 w-4" strokeWidth={1.8} />
      </button>

      {open && (
        <div className="animate-fade-in absolute right-0 top-9 z-20 w-64 overflow-hidden rounded-xl border border-edge bg-surface shadow-2xl shadow-black/50">
          {sessionId && (
            <button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(sessionId);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1200);
                } catch {
                  /* clipboard unavailable — no-op */
                }
              }}
              className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-left text-xs text-slate-400 transition hover:bg-white/[0.04]"
            >
              <span className="truncate font-mono">{sessionId}</span>
              <span className="shrink-0 text-slate-500">{copied ? "Copied" : "Copy"}</span>
            </button>
          )}
          {hasMessages && (
            <button
              onClick={() => {
                onNewChat();
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 border-t border-edge px-3.5 py-2.5 text-left text-xs font-medium text-slate-300 transition hover:bg-white/[0.04]"
            >
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.8} />
              New chat
            </button>
          )}
          <button
            onClick={() => {
              onRunInjection();
              setOpen(false);
            }}
            className="flex w-full items-center gap-2.5 border-t border-edge px-3.5 py-2.5 text-left text-xs font-medium text-red-300 transition hover:bg-red-950/30"
          >
            <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.8} />
            Run injection demo
          </button>
        </div>
      )}
    </div>
  );
}

export default function ChatPanel() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const lastUserTextRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function resetConversation() {
    setSessionId(null);
    setMessages([]);
    setInput("");
    lastUserTextRef.current = null;
    inputRef.current?.focus();
  }

  async function runInjectionDemo() {
    // Hits the real checkout path with a synthetic discount field, since a well-behaved
    // model won't attempt this in conversation.
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
          flag: "blocked",
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
    lastUserTextRef.current = text;
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
      setMessages((m) => [...m, { role: "assistant", text: data.reply, checkoutUrl: data.checkout_url }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `Something went wrong talking to the backend: ${err.message}`, error: true, retryText: text },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl border border-edge bg-surface shadow-2xl shadow-black/40 overflow-hidden">
      <div className="flex items-center justify-between border-b border-edge bg-white/[0.02] px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <h2 className="truncate text-sm font-semibold text-slate-200">Shopping assistant</h2>
          <span className="hidden shrink-0 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-500 ring-1 ring-slate-700 sm:inline">Gemini</span>
        </div>
        <HeaderMenu sessionId={sessionId} hasMessages={messages.length > 0} onNewChat={resetConversation} onRunInjection={runInjectionDemo} />
      </div>

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-5 text-center">
            <button
              onClick={() => inputRef.current?.focus()}
              className="flex h-14 w-14 items-center justify-center rounded-full bg-canvas ring-1 ring-edge text-rzp transition-all duration-200 hover:ring-rzp/40 hover:text-blue-300"
              title="Start a conversation"
            >
              <Plus className="h-7 w-7" strokeWidth={1.8} />
            </button>
            <div>
              <p className="text-sm font-medium text-slate-300">Ask about the catalog, or start a purchase</p>
              <p className="mt-1 text-xs text-slate-500">Every price and approval below comes from the server, never the model</p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 px-4">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-slate-700 bg-transparent px-4 py-2 text-sm text-slate-300 transition-colors duration-200 hover:bg-slate-800 hover:border-slate-600"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex animate-fade-in items-end gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                {m.role === "user" ? <UserAvatar /> : <AssistantAvatar />}
                <div
                  className={`max-w-[78%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap shadow-sm ${
                    m.role === "user"
                      ? "rounded-br-md bg-rzp text-white"
                      : m.error
                      ? "rounded-bl-md border border-red-900/60 bg-red-950/40 text-red-200"
                      : m.flag === "blocked"
                      ? "rounded-bl-md border border-red-900/50 bg-red-950/20 text-slate-50"
                      : "rounded-bl-md border border-edge bg-slate-800/70 text-slate-50"
                  }`}
                >
                  {m.text}
                  {m.retryText && (
                    <button
                      onClick={() => send(m.retryText)}
                      disabled={loading}
                      className="mt-2 flex items-center gap-1.5 rounded-lg border border-red-800/60 bg-red-950/30 px-2.5 py-1.5 text-xs font-medium text-red-200 transition hover:bg-red-900/40 disabled:opacity-50"
                    >
                      <RotateCcw className="h-3 w-3" strokeWidth={1.8} />
                      Retry
                    </button>
                  )}
                  {m.checkoutUrl && (
                    <a
                      href={m.checkoutUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2.5 flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500 py-2 text-xs font-semibold text-emerald-950 shadow-sm transition hover:bg-emerald-400"
                    >
                      Complete checkout
                      <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.2} />
                    </a>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex items-end gap-2">
                <AssistantAvatar />
                <div className="rounded-2xl rounded-bl-md border border-white/[0.06] bg-slate-800/70 px-3.5 py-2.5">
                  <TypingDots />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex gap-2 border-t border-edge bg-white/[0.02] p-3"
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message the shopping assistant…"
          className="flex-1 rounded-xl border border-edge bg-canvas px-3.5 py-2.5 text-sm text-slate-50 placeholder:text-slate-500 outline-none transition-all duration-200 focus:border-rzp focus:ring-2 focus:ring-rzp/20"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="flex items-center gap-1.5 rounded-xl bg-rzp px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:bg-rzp-hover hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.2} />
          ) : (
            <>
              Send
              <Send className="h-3.5 w-3.5" strokeWidth={2} />
            </>
          )}
        </button>
      </form>
    </div>
  );
}
