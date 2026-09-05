import { useEffect, useState } from "react";
import { LayoutGrid, CheckCircle2, ShieldAlert } from "lucide-react";
import { usePolling } from "./usePolling.js";

function MandateMeter({ stats }) {
  const pct = Math.min(100, Math.round((stats.spent_so_far_inr / stats.max_spend_inr) * 100));
  const tone = pct >= 90 ? "from-red-500 to-orange-500" : pct >= 60 ? "from-amber-500 to-yellow-400" : "bg-rzp";

  // Animate the fill from 0% on mount instead of snapping straight to `pct`.
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setWidth(pct));
    return () => cancelAnimationFrame(id);
  }, [pct]);

  return (
    <div className="col-span-2 rounded-xl border border-edge bg-surface p-4 shadow-xl shadow-black/30 transition-colors duration-200 hover:border-slate-700 sm:col-span-1 lg:col-span-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-rzp/15 text-rzp ring-1 ring-rzp/25">
            <LayoutGrid className="h-4 w-4" strokeWidth={1.8} />
          </div>
          <h3 className="text-sm font-semibold text-slate-200">Spend mandate</h3>
        </div>
        <span className="font-mono text-xs text-slate-400">
          <span className="font-semibold text-slate-50">₹{stats.spent_so_far_inr.toLocaleString("en-IN")}</span> / ₹
          {stats.max_spend_inr.toLocaleString("en-IN")}
        </span>
      </div>

      <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-edge">
        <div
          className={`h-full rounded-full ${tone.startsWith("bg-") ? tone : `bg-gradient-to-r ${tone}`} transition-[width] duration-1000 ease-out`}
          style={{ width: `${width}%` }}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {stats.allowed_categories.map((c) => (
          <span key={c} className="rounded-full bg-edge px-3 py-1 text-xs font-medium text-slate-300">
            {c}
          </span>
        ))}
        <span className="ml-auto text-xs text-slate-500">{pct}% of mandate used</span>
      </div>
    </div>
  );
}

function StatTile({ icon, label, value, tone }) {
  return (
    <div className="rounded-xl border border-edge bg-surface p-4 shadow-lg shadow-black/20 transition-colors duration-200 hover:border-slate-700">
      <div className={`mb-2 flex h-8 w-8 items-center justify-center rounded-lg ${tone}`}>{icon}</div>
      <div className="text-4xl font-semibold tracking-tight text-slate-50 tabular-nums">{value}</div>
      <div className="text-sm text-slate-400">{label}</div>
    </div>
  );
}

export default function StatsBar() {
  const { data: stats } = usePolling("/stats", 2000);
  if (!stats) return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 animate-pulse">{[0, 1, 2, 3].map((i) => <div key={i} className="h-[92px] rounded-xl bg-surface" />)}</div>;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MandateMeter stats={stats} />

      <StatTile
        label="Orders completed"
        value={stats.orders_count}
        tone="bg-[rgba(16,185,129,0.1)] text-[#10B981]"
        icon={<CheckCircle2 className="h-4 w-4" strokeWidth={2} />}
      />

      <StatTile
        label="Manipulation attempts blocked"
        value={stats.blocked_count}
        tone="bg-[rgba(239,68,68,0.1)] text-[#EF4444]"
        icon={<ShieldAlert className="h-4 w-4" strokeWidth={1.8} />}
      />
    </div>
  );
}
