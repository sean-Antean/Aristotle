"use client";

import { useEffect, useState } from "react";

export default function RefreshBar({ createdAt }: { createdAt: string }) {
  const [ago, setAgo] = useState<string>("");
  const [stale, setStale] = useState(false);
  const [count, setCount] = useState(0); // > 0 while a refresh is in flight

  useEffect(() => {
    const t0 = new Date(createdAt).getTime();
    const tick = () => {
      const secs = Math.max(0, Math.floor((Date.now() - t0) / 1000));
      setStale(secs > 3600);
      if (secs < 60) setAgo(`${secs}s ago`);
      else if (secs < 3600) setAgo(`${Math.floor(secs / 60)}m ago`);
      else setAgo(`${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m ago`);
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => clearInterval(id);
  }, [createdAt]);

  // countdown → reload once fresh data has had time to land
  useEffect(() => {
    if (count <= 0) return;
    const id = setTimeout(() => {
      if (count === 1) window.location.reload();
      else setCount((c) => c - 1);
    }, 1000);
    return () => clearTimeout(id);
  }, [count]);

  async function refreshNow() {
    try { await fetch("/api/refresh", { method: "POST" }); } catch {}
    setCount(75); // watcher pulls within ~1 min; then auto-reload
  }

  return (
    <div className="refreshbar">
      <span className={stale ? "text-warn" : "muted"} title={new Date(createdAt).toLocaleString()}>
        Updated {ago}
      </span>
      {count > 0 ? (
        <button className="refreshbtn" disabled>Refreshing… {count}s</button>
      ) : (
        <button className="refreshbtn" onClick={refreshNow} aria-label="Refresh now">
          &#8635; Refresh now
        </button>
      )}
    </div>
  );
}
