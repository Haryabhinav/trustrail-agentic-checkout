import { useState } from "react";
import ChatPanel from "./ChatPanel.jsx";
import AuditDashboard from "./AuditDashboard.jsx";

export default function App() {
  const [gatewayStatus, setGatewayStatus] = useState(null);

  async function armGatewayFailure(attempts) {
    const res = await fetch("/demo/simulate-gateway-failure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ attempts }),
    });
    const data = await res.json();
    setGatewayStatus(data);
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">TrustRail</h1>
          <p className="text-sm text-slate-400">
            The LLM proposes. The server disposes. Nothing the model says is ever trusted as a number.
          </p>
        </div>
        <div className="flex gap-2 text-xs">
          <button
            onClick={() => armGatewayFailure(2)}
            className="px-3 py-1.5 rounded bg-amber-900/40 border border-amber-700 text-amber-300 hover:bg-amber-900/70"
          >
            Simulate gateway failure (2 attempts)
          </button>
          {gatewayStatus && (
            <span className="px-3 py-1.5 rounded bg-slate-800 text-slate-300">
              Armed: {gatewayStatus.armed_failures} failure(s)
            </span>
          )}
        </div>
      </header>

      <main className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 h-[calc(100vh-73px)]">
        <ChatPanel />
        <AuditDashboard />
      </main>
    </div>
  );
}
