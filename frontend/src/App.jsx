import { useEffect, useState } from "react";
import { getDemoSites, screenSite } from "./api";
import MapView from "./MapView";
import Results from "./Results";
import Alerts from "./Alerts";

export default function App() {
  const [tab, setTab] = useState("screen"); // "screen" | "alerts"
  const [pin, setPin] = useState(null); // {lat, lon}
  const [mw, setMw] = useState(100);
  const [demoSites, setDemoSites] = useState([]);
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getDemoSites().then(setDemoSites).catch(() => {});
  }, []);

  function pickDemo(id) {
    const s = demoSites.find((d) => String(d.id) === id);
    if (s) {
      setPin({ lat: s.lat, lon: s.lon });
      setMw(s.mw);
    }
  }

  async function runScreen() {
    setLoading(true);
    setError("");
    setSelectedId(null);
    try {
      setResult(await screenSite(pin.lat, pin.lon, Number(mw)));
    } catch (e) {
      setError(e.message);
      setResult(null);
    }
    setLoading(false);
  }

  function openAlert(a) {
    setPin({ lat: a.lat, lon: a.lon });
    setMw(a.mw);
    setResult(a.result);
    setTab("screen");
  }

  return (
    <div className="flex h-full flex-col bg-slate-50 text-slate-800">
      <header className="flex items-center justify-between border-b bg-white px-5 py-3">
        <h1 className="text-lg font-bold">
          Site<span className="text-emerald-600">Check</span>
          <span className="ml-3 text-sm font-normal text-slate-500">What's on this land before a data center is built?</span>
        </h1>
        <nav className="flex gap-1">
          {["screen", "alerts"].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`rounded-md px-3 py-1.5 text-sm capitalize ${tab === t ? "bg-slate-800 text-white" : "hover:bg-slate-100"}`}>
              {t === "screen" ? "Screen a site" : "Alerts"}
            </button>
          ))}
        </nav>
      </header>

      <main className="flex min-h-0 flex-1">
        <aside className="w-[440px] shrink-0 overflow-y-auto border-r bg-white p-5">
          {tab === "alerts" ? (
            <Alerts onOpen={openAlert} />
          ) : (
            <>
              <div className="space-y-3">
                <select className="w-full rounded-md border px-3 py-2 text-sm" defaultValue=""
                  onChange={(e) => pickDemo(e.target.value)}>
                  <option value="" disabled>Load a demo site…</option>
                  {demoSites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <p className="text-sm text-slate-500">
                  {pin ? `Pin: ${pin.lat.toFixed(4)}, ${pin.lon.toFixed(4)}` : "Click the map to drop a pin (NJ or NY)."}
                </p>
                <label className="flex items-center gap-2 text-sm">
                  Planned capacity
                  <input type="number" min="1" value={mw} onChange={(e) => setMw(e.target.value)}
                    className="w-24 rounded-md border px-2 py-1" /> MW
                </label>
                <button onClick={runScreen} disabled={!pin || loading}
                  className="w-full rounded-md bg-emerald-600 py-2 font-medium text-white hover:bg-emerald-700 disabled:opacity-40">
                  {loading ? "Screening… (first look at a new area can take ~30s)" : "Screen site"}
                </button>
                {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
              </div>
              {result && <Results result={result} selectedId={selectedId} onSelect={setSelectedId} />}
            </>
          )}
        </aside>
        <section className="relative flex-1">
          <MapView pin={pin} onPick={(lat, lon) => { setPin({ lat, lon }); setTab("screen"); }}
            result={result} selectedId={selectedId} onSelect={setSelectedId} />
        </section>
      </main>

      <footer className="border-t bg-white px-5 py-1.5 text-xs text-slate-500">
        Screening-level only, from public GIS data. Not a site survey. Does not predict permit outcomes.
      </footer>
    </div>
  );
}
