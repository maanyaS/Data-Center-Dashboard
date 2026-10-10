import { useEffect, useState } from "react";
import { getAlerts } from "./api";

export default function Alerts({ onOpen }) {
  const [alerts, setAlerts] = useState(null);

  useEffect(() => {
    getAlerts().then(setAlerts).catch(() => setAlerts([]));
  }, []);

  if (!alerts) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div className="space-y-3">
      <h2 className="font-semibold">New large-load requests (NYISO queue)</h2>
      <p className="text-xs text-slate-500">
        Auto-screened when they appear in the public NYISO interconnection queue. Queue entries list a county,
        not an address, so locations are approximate (county center).
      </p>
      {alerts.length === 0 && <p className="text-sm text-slate-500">No alerts yet.</p>}
      {alerts.map((a) => (
        <button key={a.id} disabled={!a.result} onClick={() => onOpen(a)}
          className="w-full rounded-md border p-3 text-left text-sm hover:bg-slate-50 disabled:opacity-60">
          <div className="flex justify-between gap-2">
            <span className="font-medium">{a.name || `Queue #${a.queue_id}`}</span>
            <span className="text-xs text-slate-500">{a.mw} MW</span>
          </div>
          <div className="text-xs text-slate-500">{a.county} · queue #{a.queue_id} · {a.created_at}</div>
          <p className="mt-1">{a.summary}</p>
          <span className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Approximate location</span>
        </button>
      ))}
    </div>
  );
}
