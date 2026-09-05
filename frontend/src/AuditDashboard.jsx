import { useCallback, useMemo, useRef, useState } from "react";
import {
  ShoppingCart,
  ShieldCheck,
  Ban,
  Tag,
  RotateCcw,
  Check,
  Zap,
  CreditCard,
  Copy,
  ListTree,
} from "lucide-react";

import { usePolling } from "./usePolling.js";

const STATUS_STYLES = {
  ok: { badge: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30", dot: "bg-emerald-400", ring: "ring-emerald-500/30", icon: "text-emerald-300 bg-emerald-500/15", glow: "ring-emerald-400/50 shadow-emerald-500/20" },
  blocked: { badge: "bg-red-500/15 text-red-300 ring-red-500/30", dot: "bg-red-400", ring: "ring-red-500/30", icon: "text-red-300 bg-red-500/15", glow: "ring-red-400/50 shadow-red-500/20" },
  error: { badge: "bg-red-500/15 text-red-300 ring-red-500/30", dot: "bg-red-400", ring: "ring-red-500/30", icon: "text-red-300 bg-red-500/15", glow: "ring-red-400/50 shadow-red-500/20" },
  retrying: { badge: "bg-amber-500/15 text-amber-300 ring-amber-500/30", dot: "bg-amber-400", ring: "ring-amber-500/30", icon: "text-amber-300 bg-amber-500/15", glow: "ring-amber-400/50 shadow-amber-500/20" },
  pending: { badge: "bg-slate-500/15 text-slate-300 ring-slate-500/30", dot: "bg-slate-400", ring: "ring-slate-500/30", icon: "text-slate-300 bg-slate-500/15", glow: "ring-slate-400/50 shadow-slate-500/20" },
};

function statusStyle(status) {
  return STATUS_STYLES[status] || STATUS_STYLES.pending;
}

const EVENT_META = {
  order_created: { label: "Order created", icon: "cart" },
  mandate_check: { label: "Mandate check", icon: "shield" },
  rejected_injection: { label: "Injection rejected", icon: "block" },
  price_mismatch_corrected: { label: "Price corrected", icon: "tag" },
  gateway_retry: { label: "Gateway retry", icon: "retry" },
  payment_captured: { label: "Payment captured", icon: "check" },
  webhook_received: { label: "Webhook received", icon: "bolt" },
  autopay_charge: { label: "Autopay charge", icon: "bolt" },
  autopay_setup_started: { label: "Autopay setup started", icon: "card" },
  autopay_token_saved: { label: "Autopay token saved", icon: "check" },
  autopay_revoked: { label: "Autopay revoked", icon: "block" },
};

const ICONS = {
  cart: ShoppingCart,
  shield: ShieldCheck,
  block: Ban,
  tag: Tag,
  retry: RotateCcw,
  check: Check,
  bolt: Zap,
  card: CreditCard,
};

function EventIcon({ name, className }) {
  const Icon = ICONS[name] || ICONS.shield;
  return <Icon className={className} strokeWidth={1.8} />;
}

function CopyButton({ value }) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;
  return (
    <button
      type="button"
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          /* clipboard unavailable — ignore */
        }
      }}
      className="ml-1 inline-flex items-center rounded p-0.5 text-slate-600 transition hover:text-slate-300"
      title={`Copy ${value}`}
    >
      {copied ? <Check className="h-3 w-3 text-emerald-400" strokeWidth={2.2} /> : <Copy className="h-3 w-3" strokeWidth={1.6} />}
    </button>
  );
}

function ProposeDiff({ row }) {
  if (!row.llm_said && !row.server_used) return null;
  const diverges = row.event_type === "rejected_injection" || row.event_type === "price_mismatch_corrected";
  return (
    <div className="mt-2.5 grid grid-cols-2 gap-2 font-mono text-[10.5px] leading-relaxed">
      <div className={`rounded border p-2 ${diverges ? "border-red-500/25 bg-red-500/[0.06]" : "border-slate-800 bg-slate-900"}`}>
        <div className="mb-1 flex items-center gap-1 text-slate-500">
          <span className="h-1 w-1 rounded-full bg-slate-500" /> llm_said
        </div>
        <div className="break-all text-slate-400">{row.llm_said || "—"}</div>
      </div>
      <div className={`rounded border p-2 ${diverges ? "border-emerald-500/25 bg-emerald-500/[0.06]" : "border-slate-800 bg-slate-900"}`}>
        <div className="mb-1 flex items-center gap-1 text-slate-500">
          <span className="h-1 w-1 rounded-full bg-slate-500" /> server_used
        </div>
        <div className="break-all text-slate-400">{row.server_used || "—"}</div>
      </div>
    </div>
  );
}

function AuditRow({ row, isLast, isNew }) {
  const style = statusStyle(row.status);
  const meta = EVENT_META[row.event_type] || { label: row.event_type, icon: "shield" };

  return (
    <div className="animate-fade-in relative flex gap-3 pb-4">
      {!isLast && <span className="absolute left-[15px] top-8 bottom-0 w-px bg-slate-800" />}

      <div className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ring-1 ${style.icon} ${style.ring}`}>
        <EventIcon name={meta.icon} className="h-4 w-4" />
      </div>

      <div
        className={`min-w-0 flex-1 rounded-xl border border-edge bg-canvas/60 p-3 transition-all duration-700 hover:border-slate-700 hover:bg-surface ${
          isNew ? `ring-2 ${style.glow} shadow-lg` : ""
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-[13px] font-semibold text-slate-100">{meta.label}</span>
          <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${style.badge}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${style.dot} ${row.status === "retrying" ? "animate-pulse-dot" : ""}`} />
            {row.status}
          </span>
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
          <span className="flex items-center font-mono">
            {row.session_id?.slice(0, 10)}
            <CopyButton value={row.session_id} />
          </span>
          {row.canonical_price_inr != null && <span className="font-medium text-slate-400">₹{row.canonical_price_inr}</span>}
          {row.mandate_check_result !== "na" && (
            <span className={row.mandate_check_result === "pass" ? "text-emerald-400/80" : "text-red-400/80"}>
              mandate: {row.mandate_check_result}
            </span>
          )}
          {row.razorpay_order_id && (
            <span className="flex items-center font-mono">
              {row.razorpay_order_id}
              <CopyButton value={row.razorpay_order_id} />
            </span>
          )}
          <span className="ml-auto tabular-nums">{row.timestamp && new Date(row.timestamp).toLocaleTimeString()}</span>
        </div>

        <ProposeDiff row={row} />
      </div>
    </div>
  );
}

const FILTERS = [
  { key: "all", label: "All" },
  { key: "orders", label: "Orders", match: (r) => r.event_type === "order_created" || r.event_type === "autopay_charge" || r.event_type === "payment_captured" },
  { key: "blocked", label: "Blocked", match: (r) => r.status === "blocked" || r.status === "error" },
  { key: "retrying", label: "Retries", match: (r) => r.status === "retrying" },
];

export default function AuditDashboard() {
  const [filter, setFilter] = useState("all");
  const [newIds, setNewIds] = useState(() => new Set());
  const seenIds = useRef(new Set());

  const onData = useCallback((data) => {
    const freshlyArrived = data.filter((r) => !seenIds.current.has(r.id)).map((r) => r.id);
    if (freshlyArrived.length && seenIds.current.size > 0) {
      // Skip the initial load so old rows don't all flash at once.
      setNewIds(new Set(freshlyArrived));
      setTimeout(() => setNewIds(new Set()), 2200);
    }
    data.forEach((r) => seenIds.current.add(r.id));
  }, []);

  const { data, error } = usePolling("/audit?limit=100", 1500, { onData });
  const rows = data || [];

  const visibleRows = useMemo(() => {
    const active = FILTERS.find((f) => f.key === filter);
    return active?.match ? rows.filter(active.match) : rows;
  }, [rows, filter]);

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-edge bg-surface shadow-2xl shadow-black/40 overflow-hidden">
      <div className="border-b border-slate-800 bg-white/[0.02] px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rzp opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-rzp" />
            </span>
            <h2 className="text-sm font-semibold text-slate-200">Audit trail</h2>
          </div>
          <span className="text-[11px] text-slate-500">
            {visibleRows.length} of {rows.length}
            {error && <span className="text-red-400"> — {error}</span>}
          </span>
        </div>

        <div className="mt-2.5 flex gap-1.5">
          {FILTERS.map((f) => {
            const count = f.match ? rows.filter(f.match).length : rows.length;
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition ${
                  filter === f.key
                    ? "bg-slate-700 text-white"
                    : "bg-edge text-slate-500 hover:text-slate-300"
                }`}
              >
                {f.label}
                {count > 0 && <span className="ml-1 opacity-60">{count}</span>}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        {rows.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-600">
            <ListTree className="h-8 w-8 opacity-40" strokeWidth={1.6} />
            <p className="text-xs">No events yet — start a chat to see the audit trail.</p>
          </div>
        ) : visibleRows.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-600">
            <p className="text-xs">No events match this filter yet.</p>
          </div>
        ) : (
          visibleRows.map((row, i) => (
            <AuditRow key={row.id} row={row} isLast={i === visibleRows.length - 1} isNew={newIds.has(row.id)} />
          ))
        )}
      </div>
    </div>
  );
}
