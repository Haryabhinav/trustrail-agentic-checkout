import { createContext, useCallback, useContext, useRef, useState } from "react";

const ToastContext = createContext(null);

const TONE_STYLES = {
  success: { ring: "ring-emerald-500/30", icon: "bg-emerald-500/15 text-emerald-300", bar: "bg-emerald-400" },
  error: { ring: "ring-red-500/30", icon: "bg-red-500/15 text-red-300", bar: "bg-red-400" },
  info: { ring: "ring-rzp/30", icon: "bg-rzp/15 text-blue-300", bar: "bg-rzp" },
};

const TONE_ICON = {
  success: <path d="M5 12.5l4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />,
  error: (
    <>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 8v5m0 3h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 11v5m0-8h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </>
  ),
};

const DEFAULT_DURATION_MS = 4200;

function ToastItem({ toast, onDismiss }) {
  const style = TONE_STYLES[toast.tone] || TONE_STYLES.info;
  return (
    <div
      role="status"
      className={`animate-fade-in pointer-events-auto relative w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-edge bg-surface p-3.5 pr-8 shadow-2xl shadow-black/50 ring-1 ${style.ring}`}
    >
      <span className={`absolute left-0 top-0 bottom-0 w-[3px] ${style.bar}`} />
      <div className="flex items-start gap-2.5">
        <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${style.icon}`}>
          <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5">
            {TONE_ICON[toast.tone] || TONE_ICON.info}
          </svg>
        </div>
        <div className="min-w-0 pt-0.5">
          {toast.title && <p className="text-[13px] font-semibold text-slate-50">{toast.title}</p>}
          {toast.message && <p className="mt-0.5 text-[12px] leading-relaxed text-slate-400">{toast.message}</p>}
        </div>
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="absolute right-2 top-2 rounded p-1 text-slate-600 transition hover:bg-white/5 hover:text-slate-300"
        aria-label="Dismiss"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
          <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const push = useCallback(
    (tone, title, message, duration = DEFAULT_DURATION_MS) => {
      const id = ++idRef.current;
      setToasts((t) => [...t, { id, tone, title, message }]);
      setTimeout(() => dismiss(id), duration);
      return id;
    },
    [dismiss]
  );

  const api = {
    success: (title, message) => push("success", title, message),
    error: (title, message) => push("error", title, message),
    info: (title, message) => push("info", title, message),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col-reverse gap-2">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
