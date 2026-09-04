import { useState } from "react";
import ChatPanel from "./ChatPanel.jsx";
import AuditDashboard from "./AuditDashboard.jsx";
import AutopayPanel from "./AutopayPanel.jsx";
import StatsBar from "./StatsBar.jsx";
import { useToast } from "./Toast.jsx";

function ShieldMark() {
  return (
    <div className="relative h-9 w-9 shrink-0 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-950/50 flex items-center justify-center ring-1 ring-white/10">
      <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none">
        <path
          d="M12 2.5l7.5 3v5.2c0 4.7-3.2 8.9-7.5 10.3-4.3-1.4-7.5-5.6-7.5-10.3V5.5l7.5-3z"
          fill="currentColor"
          fillOpacity="0.18"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path d="M8.7 12.2l2.4 2.4 4.4-4.9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

export default function App() {
  const [armedCount, setArmedCount] = useState(0);
  const [arming, setArming] = useState(false);
  const toast = useToast();

  async function armGatewayFailure(attempts) {
    setArming(true);
    try {
      const res = await fetch("/demo/simulate-gateway-failure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ attempts }),
      });
      const data = await res.json();
      setArmedCount(data.armed_failures);
      toast.info(
        "Gateway failure armed",
        `The next ${data.armed_failures} Razorpay order-creation attempt(s) will fail — try a purchase to watch the retry ladder in the audit trail.`
      );
    } catch (err) {
      toast.error("Couldn't arm gateway failure", err.message);
    } finally {
      setArming(false);
    }
  }

  return (
    <div className="min-h-screen text-slate-100">
      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-[#05070d]/80 backdrop-blur-xl px-4 sm:px-6 py-3.5">
        <div className="mx-auto max-w-7xl flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <ShieldMark />
            <div className="min-w-0">
              <h1 className="text-[17px] font-bold tracking-tight bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
                TrustRail
              </h1>
              <p className="text-[11px] text-slate-500 leading-tight truncate">
                The LLM proposes. The server disposes.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => armGatewayFailure(2)}
              disabled={arming}
              className="group flex items-center gap-1.5 rounded-lg border border-amber-800/60 bg-amber-950/30 px-3 py-1.5 text-xs font-medium text-amber-300 transition hover:border-amber-700 hover:bg-amber-900/40 disabled:opacity-50"
            >
              <svg className="h-3.5 w-3.5 opacity-80 transition group-hover:rotate-12" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 9v4m0 4h.01M10.3 3.9L2.5 17a1.5 1.5 0 001.3 2.2h16.4a1.5 1.5 0 001.3-2.2L13.7 3.9a1.5 1.5 0 00-2.6 0z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Simulate gateway failure
            </button>
            {armedCount > 0 && (
              <span className="animate-fade-in rounded-lg bg-slate-800/70 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 ring-1 ring-white/[0.06]">
                Armed ×{armedCount}
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 pt-5 space-y-4">
        <StatsBar />
        <AutopayPanel />
      </div>

      <main className="mx-auto max-w-7xl grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 sm:p-6 items-stretch h-[720px] max-h-[calc(100vh-15rem)] lg:max-h-[calc(100vh-16rem)]">
        <ChatPanel />
        <AuditDashboard />
      </main>

      <footer className="mx-auto max-w-7xl px-4 sm:px-6 pb-6 pt-1 text-center text-[11px] text-slate-600">
        Razorpay AI Buildathon 2026 · Track 01 — AI Growth &amp; Agentic Commerce
      </footer>
    </div>
  );
}
