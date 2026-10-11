import { useEffect, useState } from "react";
import { getProjects, screenSite } from "./api";
import MapView from "./MapView";
import Results from "./Results";
import Alerts from "./Alerts";
import Search from "./Search";
import Alternatives from "./Alternatives";

export default function App() {
  const [tab, setTab] = useState("screen"); // "screen" | "alerts"
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null); // selected existing project, or null for a new proposal
  const [pin, setPin] = useState(null); // {lat, lon}
  const [name, setName] = useState("");
  const [mw, setMw] = useState(100);
  const [withPopulation, setWithPopulation] = useState(false);
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [alts, setAlts] = useState(null); // nearby lower-risk candidates shown on the map

  useEffect(() => {
    getProjects().then(setProjects).catch(() => {});
  }, []);

  function reset(next) {
    setResult(null);
    setSelectedId(null);
    setError("");
    setAlts(null);
    setTab("screen");
    next();
  }

  // Clicked an existing project (map pin, search, or alert)
  const openProject = (p) => reset(() => {
    setProject(p);
    setPin({ lat: p.lat, lon: p.lon });
    setName(p.name);
    setMw(p.mw || 100);
  });

  // Clicked an empty spot / searched a place -> new proposed data center
  const dropPin = ({ lat, lon }) => reset(() => {
    setProject(null);
    setPin({ lat, lon });
    if (project) setName("");
  });

  async function runScreen() {
    setLoading(true);
    setError("");
    setSelectedId(null);
    setAlts(null);
    try {
      setResult(await screenSite(pin.lat, pin.lon, Number(mw), name, withPopulation));
    } catch (e) {
      setError(e.message);
      setResult(null);
    }
    setLoading(false);
  }

  function openAlert(a) {
    openProject({ name: a.name, lat: a.lat, lon: a.lon, mw: a.mw, county: a.county, state: "NY",
      source: "nyiso", approximate: 1, notes: a.summary });
    setResult(a.result);
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
              className={`rounded-md px-3 py-1.5 text-sm ${tab === t ? "bg-slate-800 text-white" : "hover:bg-slate-100"}`}>
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
                <Search projects={projects} onProject={openProject} onPlace={dropPin} />

                {!pin && (
                  <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">
                    Click a <b className="text-violet-600">project pin</b> to screen a known data center, or click
                    anywhere in the US to test a <b className="text-emerald-600">proposed</b> one.
                  </p>
                )}

                {pin && (project ? <ProjectCard p={project} /> : (
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
                    <div className="font-medium text-emerald-800">New proposed data center</div>
                    <div className="text-xs text-emerald-700">Pin: {pin.lat.toFixed(4)}, {pin.lon.toFixed(4)}</div>
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project / company name (optional)"
                      className="mt-2 w-full rounded-md border bg-white px-2 py-1" />
                  </div>
                ))}

                {pin && (
                  <>
                    <label className="flex items-center gap-2 text-sm">
                      Planned capacity
                      <input type="number" min="1" value={mw} onChange={(e) => setMw(e.target.value)}
                        className="w-24 rounded-md border px-2 py-1" /> MW
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input type="checkbox" checked={withPopulation} onChange={(e) => setWithPopulation(e.target.checked)} />
                      Include population nearby (2020 Census, slower)
                    </label>
                    <button onClick={runScreen} disabled={loading}
                      className="w-full rounded-md bg-emerald-600 py-2 font-medium text-white hover:bg-emerald-700 disabled:opacity-40">
                      {loading ? "Screening… (a new area can take ~30s)" : "Screen site"}
                    </button>
                  </>
                )}
                {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
              </div>
              {result && <Results result={result} selectedId={selectedId} onSelect={setSelectedId} />}
              {result && <Alternatives key={`${result.site.lat},${result.site.lon},${result.site.mw}`} result={result}
                onFound={setAlts} onGo={(c) => dropPin({ lat: c.lat, lon: c.lon })} />}
            </>
          )}
        </aside>
        <section className="relative flex-1">
          <MapView pin={pin} projects={projects} onPick={(lat, lon) => dropPin({ lat, lon })} onProject={openProject}
            result={result} selectedId={selectedId} onSelect={setSelectedId} alts={alts} />
        </section>
      </main>

      <footer className="border-t bg-white px-5 py-1.5 text-xs text-slate-500">
        Screening-level only, from public GIS data. Not a site survey. Does not predict permit outcomes.
      </footer>
    </div>
  );
}

function ProjectCard({ p }) {
  return (
    <div className="rounded-md border border-violet-200 bg-violet-50 p-3 text-sm">
      <div className="flex justify-between gap-2">
        <span className="font-medium text-violet-900">{p.name}</span>
        <span className="text-xs text-violet-700">{{ nyiso: "NYISO queue", fractracker: "FracTracker Alliance", list: "SJ Climate News list" }[p.source] || p.source}</span>
      </div>
      <div className="text-xs text-violet-700">{p.county}, {p.state}{p.status ? ` · ${p.status}` : ""}</div>
      {p.notes && <p className="mt-1 text-xs text-slate-600">{p.notes}</p>}
      {p.approximate ? <span className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Approximate location</span> : null}
    </div>
  );
}
