import { useEffect, useState } from "react";
import { Loader2, CreditCard, Zap } from "lucide-react";
import { useToast } from "./Toast.jsx";

// Razorpay's fraud heuristic rejects contact numbers with 4+ repeating digits.
function contactIssue(contact) {
  if (!contact) return null;
  if (!/^\d{10}$/.test(contact)) return "Enter exactly 10 digits";
  if (/(\d)\1{3,}/.test(contact)) return "Razorpay rejects numbers with 4+ repeated digits, even in test mode";
  return null;
}

export default function AutopayPanel() {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", contact: "" });
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const contactError = form.contact ? contactIssue(form.contact) : null;

  async function refreshStatus() {
    const res = await fetch("/autopay/status");
    setStatus(await res.json());
  }

  useEffect(() => {
    refreshStatus();
  }, []);

  async function saveCard(e) {
    e.preventDefault();
    if (contactIssue(form.contact)) {
      toast.error("Check the contact number", contactIssue(form.contact));
      return;
    }
    setBusy(true);
    try {
      const setupRes = await fetch("/autopay/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const setup = await setupRes.json();
      if (!setupRes.ok) throw new Error(setup.detail || "setup failed");

      // The one human-authenticated payment that tokenizes the card.
      const rzp = new window.Razorpay({
        key: setup.key_id,
        order_id: setup.order_id,
        amount: setup.amount_paise,
        currency: setup.currency,
        name: "PayPilot",
        description: "Save card for agent autopay (₹1 authorization)",
        recurring: "1",
        prefill: { name: setup.name, email: setup.email, contact: setup.contact },
        theme: { color: "#3366FF" },
        handler: async function (response) {
          const confirmRes = await fetch("/autopay/confirm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            }),
          });
          const confirmed = await confirmRes.json();
          if (confirmed.ok) {
            toast.success("Card saved", "The agent can now complete purchases with zero human interaction.");
          } else {
            toast.error("Card save failed", confirmed.error);
          }
          await refreshStatus();
          setBusy(false);
        },
        modal: { ondismiss: () => setBusy(false) },
      });
      rzp.open();
    } catch (err) {
      toast.error("Setup failed", err.message);
      setBusy(false);
    }
  }

  async function triggerAgentPurchase() {
    setBusy(true);
    try {
      const res = await fetch("/demo/agent-autopay-purchase", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_id: 1, qty: 1 }),
      });
      const data = await res.json();
      if (data.charged_directly) {
        toast.success("Charged automatically", `₹${data.canonical_total_inr} via payment ${data.payment_id} — zero human interaction.`);
      } else {
        toast.error("Not charged", data.reason);
      }
    } catch (err) {
      toast.error("Request failed", err.message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    setBusy(true);
    await fetch("/autopay/revoke", { method: "POST" });
    await refreshStatus();
    toast.info("Autopay revoked", "The saved card can no longer be charged by the agent.");
    setBusy(false);
  }

  if (!status) return null;

  return (
    <div className="rounded-xl border border-edge bg-surface p-4 shadow-xl shadow-black/30 transition-colors duration-200 hover:border-slate-700">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-rzp/15 text-rzp ring-1 ring-rzp/25">
          <CreditCard className="h-4 w-4" strokeWidth={1.8} />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Agent autopay</h3>
          <p className="text-xs text-slate-400">Zero-touch purchases after one human-authenticated card save</p>
        </div>
      </div>

      {status.status === "active" ? (
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-edge bg-canvas/40 px-3 py-2 text-xs text-slate-300">
            <span className="flex h-1.5 w-1.5 rounded-full bg-[#10B981]" />
            {status.card_network} •••• {status.card_last4}
          </div>
          <button
            onClick={triggerAgentPurchase}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-800/60 bg-emerald-950/30 px-3 py-2 text-xs font-medium text-emerald-300 transition-all duration-200 hover:border-emerald-700 hover:bg-emerald-900/40 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.2} /> : <Zap className="h-3.5 w-3.5" strokeWidth={1.8} />}
            Trigger agent purchase
          </button>
          <button
            onClick={revoke}
            disabled={busy}
            className="rounded-lg border border-edge bg-canvas/40 px-3 py-2 text-xs font-medium text-slate-400 transition-all duration-200 hover:border-slate-600 hover:text-slate-200 disabled:opacity-50"
          >
            Revoke
          </button>
        </div>
      ) : (
        <form onSubmit={saveCard} className="flex flex-wrap items-end gap-2.5">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Name</label>
            <input
              required
              placeholder="Jane Doe"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-sm text-slate-50 placeholder-slate-600 outline-none transition-all duration-200 focus:border-rzp focus:ring-2 focus:ring-rzp/20"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Email</label>
            <input
              required
              type="email"
              placeholder="jane@example.com"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-sm text-slate-50 placeholder-slate-600 outline-none transition-all duration-200 focus:border-rzp focus:ring-2 focus:ring-rzp/20"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Contact</label>
            <input
              required
              placeholder="88XXXXXXX"
              value={form.contact}
              onChange={(e) => setForm({ ...form, contact: e.target.value.replace(/\D/g, "").slice(0, 10) })}
              className={`w-32 rounded-lg border bg-transparent px-3 py-2 text-sm text-slate-50 placeholder-slate-600 outline-none transition-all duration-200 focus:ring-2 ${
                contactError ? "border-amber-600/60 focus:border-amber-500 focus:ring-amber-500/20" : "border-slate-700 focus:border-rzp focus:ring-rzp/20"
              }`}
            />
            {contactError && <span className="text-[10px] leading-tight text-amber-400/90">{contactError}</span>}
          </div>
          <button
            type="submit"
            disabled={busy || Boolean(contactError)}
            className="flex items-center gap-1.5 rounded-lg bg-rzp px-4 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:bg-rzp-hover hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.2} />}
            Save card for autopay (₹1 one-time)
          </button>
        </form>
      )}
    </div>
  );
}
