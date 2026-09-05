import { useEffect, useRef, useState } from "react";

/** Fetches `url` every `intervalMs`, paused while the tab is hidden. `onData` runs on every
 * successful fetch for callers that need a side effect beyond storing the latest value. */
export function usePolling(url, intervalMs, { onData } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);
  const onDataRef = useRef(onData);
  onDataRef.current = onData;

  useEffect(() => {
    async function poll() {
      if (document.hidden) return;
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`server returned ${res.status}`);
        const json = await res.json();
        setData(json);
        setError(null);
        onDataRef.current?.(json);
      } catch (err) {
        setError(err.message);
      }
    }

    poll();
    intervalRef.current = setInterval(poll, intervalMs);

    function onVisibilityChange() {
      if (!document.hidden) poll();
    }
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      clearInterval(intervalRef.current);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [url, intervalMs]);

  return { data, error };
}
