import { useEffect, useRef, useState } from "react";

function usePolling(url, intervalMs) {
  const [data, setData] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    async function poll() {
      if (document.hidden) return;
      try {
        const res = await fetch(url);
        if (res.ok) setData(await res.json());
      } catch {
        /* keep last known value on transient failure */
      }
    }
    poll();
    ref.current = setInterval(poll, intervalMs);
    const onVisible = () => !document.hidden && poll();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(ref.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [url, intervalMs]);

  return data;
}

function MandateMeter({ stats }) {
  const pct = Math.min(100, Math.round((stats.spent_so_far_inr / stats.max_spend_inr) * 100));
  const tone = pct >= 90 ? "from-red-500 to-orange-500" : pct >= 60 ? "from-amber-500 to-yellow-400" : "from-emerald-500 to-teal-400";

  return (
    <div className="col-span-2 rounded-2xl border border-white/[0.07] bg-gradient-to-br from-slate-900/70 to-slate-900/30 p-4 shadow-xl shadow-black/30 backdrop-blur-sm sm:col-span-1 lg:col-span-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/25">
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
              <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
            </svg>
          </div>
          <h3 className="text-sm font-semibold text-slate-200">Spend mandate</h3>
        </div>
        <span className="font-mono text-xs text-slate-400">
          <span className="font-semibold text-slate-100">₹{stats.spent_so_far_inr.toLocaleString("en-IN")}</span> / ₹
          {stats.max_spend_inr.toLocaleString("en-IN")}
        </span>
      </div>

      <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${tone} transition-all duration-700 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {stats.allowed_categories.map((c) => (
          <span key={c} className="rounded-full bg-white/[0.04] px-2 py-0.5 text-[10px] font-medium text-slate-400 ring-1 ring-white/[0.06]">
            {c}
          </span>
        ))}
        <span className="ml-auto text-[11px] text-slate-500">{pct}% of mandate used</span>
      </div>
    </div>
  );
}

function StatTile({ icon, label, value, tone }) {
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4 shadow-lg shadow-black/20 backdrop-blur-sm">
      <div className={`mb-2 flex h-7 w-7 items-center justify-center rounded-lg ring-1 ${tone}`}>{icon}</div>
      <div className="text-2xl font-bold tracking-tight text-slate-100 tabular-nums">{value}</div>
      <div className="text-[11px] text-slate-500">{label}</div>
    </div>
  );
}

export default function StatsBar() {
  const stats = usePolling("/stats", 2000);
  if (!stats) return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 animate-pulse">{[0, 1, 2, 3].map((i) => <div key={i} className="h-[92px] rounded-2xl bg-white/[0.03]" />)}</div>;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MandateMeter stats={stats} />

      <StatTile
        label="Orders completed"
        value={stats.orders_count}
        tone="bg-emerald-500/15 text-emerald-300 ring-emerald-500/25"
        icon={
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
            <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
      />

      <StatTile
        label="Manipulation attempts blocked"
        value={stats.blocked_count}
        tone="bg-red-500/15 text-red-300 ring-red-500/25"
        icon={
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
            <path d="M12 9v4m0 4h.01M4.9 19h14.2a1 1 0 00.87-1.5L12.87 4.5a1 1 0 00-1.74 0L4.03 17.5A1 1 0 004.9 19z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
      />
    </div>
  );
}
