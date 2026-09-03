import { useEffect, useRef, useState } from "react";

const STATUS_STYLES = {
  ok: "border-emerald-700 bg-emerald-950/40 text-emerald-300",
  blocked: "border-red-700 bg-red-950/40 text-red-300",
  error: "border-red-700 bg-red-950/40 text-red-300",
  retrying: "border-amber-700 bg-amber-950/40 text-amber-300",
  pending: "border-slate-600 bg-slate-800/60 text-slate-300",
};

function statusClass(status) {
  return STATUS_STYLES[status] || "border-slate-700 bg-slate-800/40 text-slate-300";
}

function ProposeDiff({ row }) {
  if (!row.llm_said && !row.server_used) return null;
  const diverges = row.event_type === "rejected_injection" || row.event_type === "price_mismatch_corrected";
  return (
    <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] font-mono">
      <div className={`rounded p-1.5 ${diverges ? "bg-red-950/50 border border-red-800" : "bg-slate-900/60 border border-slate-800"}`}>
        <div className="text-slate-500 mb-0.5">llm_said</div>
        <div className="break-all text-slate-300">{row.llm_said || "—"}</div>
      </div>
      <div className={`rounded p-1.5 ${diverges ? "bg-emerald-950/50 border border-emerald-800" : "bg-slate-900/60 border border-slate-800"}`}>
        <div className="text-slate-500 mb-0.5">server_used</div>
        <div className="break-all text-slate-300">{row.server_used || "—"}</div>
      </div>
    </div>
  );
}

export default function AuditDashboard() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    async function poll() {
      // Skip the network round trip entirely while the tab is backgrounded (e.g. presenting
      // slides during the pitch) — no viewer benefits from a fetch nobody's about to see, and
      // it's needless load on the backend for the duration the tab stays hidden.
      if (document.hidden) return;
      try {
        const res = await fetch("/audit?limit=100");
        if (!res.ok) throw new Error(`server returned ${res.status}`);
        setRows(await res.json());
        setError(null);
      } catch (err) {
        setError(err.message);
      }
    }

    poll();
    pollRef.current = setInterval(poll, 1500);

    // Catch up immediately on return instead of waiting up to 1.5s for the next tick, so the
    // dashboard doesn't look stale for a beat right when the presenter tabs back in.
    function onVisibilityChange() {
      if (!document.hidden) poll();
    }
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      clearInterval(pollRef.current);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  return (
    <div className="flex flex-col rounded-lg border border-slate-800 bg-slate-900/50 overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between">
        <h2 className="font-medium text-sm text-slate-300">Audit trail (live)</h2>
        <span className="text-xs text-slate-500">{rows.length} events{error ? ` — ${error}` : ""}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {rows.length === 0 && <div className="text-xs text-slate-500">No events yet — start a chat.</div>}
        {rows.map((row) => (
          <div key={row.id} className={`rounded border px-3 py-2 text-xs ${statusClass(row.status)}`}>
            <div className="flex items-center justify-between">
              <span className="font-semibold">{row.event_type}</span>
              <span className="uppercase tracking-wide text-[10px] opacity-80">{row.status}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-slate-400">
              <span>session: {row.session_id?.slice(0, 8)}</span>
              {row.canonical_price_inr != null && <span>₹{row.canonical_price_inr}</span>}
              {row.mandate_check_result !== "na" && <span>mandate: {row.mandate_check_result}</span>}
              {row.razorpay_order_id && <span>order: {row.razorpay_order_id}</span>}
              <span>{row.timestamp && new Date(row.timestamp).toLocaleTimeString()}</span>
            </div>
            <ProposeDiff row={row} />
          </div>
        ))}
      </div>
    </div>
  );
}
