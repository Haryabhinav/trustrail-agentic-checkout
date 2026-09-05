import { useState } from "react";
import { ShieldCheck, AlertTriangle } from "lucide-react";
import ChatPanel from "./ChatPanel.jsx";
import AuditDashboard from "./AuditDashboard.jsx";
import AutopayPanel from "./AutopayPanel.jsx";
import StatsBar from "./StatsBar.jsx";
import { useToast } from "./Toast.jsx";

function ShieldMark() {
  return (
    <div className="relative h-9 w-9 shrink-0 rounded-xl bg-gradient-to-br from-rzp to-blue-700 shadow-lg shadow-rzp/30 flex items-center justify-center ring-1 ring-white/10">
      <ShieldCheck className="h-5 w-5 text-white" strokeWidth={2} />
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
    <div className="min-h-screen text-slate-50">
      <header className="animate-rise-in sticky top-0 z-20 border-b border-edge bg-canvas/80 backdrop-blur-xl px-4 sm:px-6 py-3.5">
        <div className="mx-auto max-w-7xl flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <ShieldMark />
            <div className="min-w-0">
              <h1 className="text-xl font-bold tracking-tight text-white">PayPilot</h1>
              <p className="text-sm text-slate-400 leading-tight truncate">
                The LLM proposes. The server disposes.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => armGatewayFailure(2)}
              disabled={arming}
              className="group flex items-center gap-1.5 rounded-lg border border-amber-900/60 bg-amber-950/30 px-3 py-1.5 text-xs font-medium text-amber-400 transition-all duration-200 hover:border-amber-700 hover:bg-amber-900/40 disabled:opacity-50"
            >
              <AlertTriangle className="h-3.5 w-3.5 animate-pulse-slow opacity-90 transition group-hover:rotate-12" strokeWidth={1.8} />
              Simulate gateway failure
            </button>
            {armedCount > 0 && (
              <span className="animate-fade-in rounded-lg bg-edge/70 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 ring-1 ring-white/[0.06]">
                Armed ×{armedCount}
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="animate-rise-in mx-auto max-w-7xl px-4 sm:px-6 pt-5 space-y-4" style={{ animationDelay: "100ms" }}>
        <StatsBar />
        <AutopayPanel />
      </div>

      <main
        className="animate-rise-in mx-auto max-w-7xl grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 sm:p-6 items-stretch h-[720px] max-h-[calc(100vh-15rem)] lg:max-h-[calc(100vh-16rem)]"
        style={{ animationDelay: "200ms" }}
      >
        <ChatPanel />
        <AuditDashboard />
      </main>

      <footer className="mx-auto max-w-7xl px-4 sm:px-6 pb-6 pt-1 text-center text-[11px] text-slate-600">
        Razorpay AI Buildathon 2026 · Track 01 — AI Growth &amp; Agentic Commerce
      </footer>
    </div>
  );
}
