import { useEffect, useState } from "react";
import { fetchBriefs, getProjects, screenSite } from "./api";
import MapView from "./MapView";
import Results from "./Results";
import Alerts from "./Alerts";
import Search from "./Search";
import Alternatives from "./Alternatives";
import ErrorBoundary from "./ErrorBoundary";
import Fps from "./Fps";
import Term from "./Term";

// One-click demo sites (already-screened areas answer in a few seconds)
const EXAMPLES = [
  { label: "Wetlands & parkland", where: "Princeton, NJ", lat: 40.3573, lon: -74.6672, mw: 200 },
  { label: "Suburban industrial edge", where: "Chicago area, IL", lat: 41.88, lon: -87.95, mw: 300 },
];
// Side panel width limits (px); the map always keeps at least MAP_MIN
const PANEL_DEFAULT = 440, PANEL_MIN = 280, MAP_MIN = 320;
const clampPanel = (w) => Math.round(Math.max(PANEL_MIN, Math.min(w, window.innerWidth - MAP_MIN)));
// Shown one after another while a screening runs
const STEPS = ["Finding the county and state…", "Checking wetlands…", "Checking flood zones…", "Checking protected land and habitat…",
  "Measuring distance to power lines…", "Applying permit rules…", "Estimating water, power and CO₂…"];

export default function App() {
  const [tab, setTab] = useState("screen"); // "screen" | "alerts"
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null); // selected existing project, or null for a new proposal
  const [pin, setPin] = useState(null); // {lat, lon}
  const [name, setName] = useState("");
  const [mw, setMw] = useState(100);
  const [withPopulation, setWithPopulation] = useState(false);
  const [radius, setRadius] = useState(5); // km: how far to look for the nearest wetland, park, etc.
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [alts, setAlts] = useState(null); // nearby lower-risk candidates shown on the map
  const [mapOnly, setMapOnly] = useState(false); // hide the side panel
  // Side panel width (drag the divider; remembered in this browser)
  const [panelW, setPanelW] = useState(() => {
    try { const w = Number(localStorage.getItem("panelWidth")); if (w) return clampPanel(w); } catch {}
    return PANEL_DEFAULT;
  });
  useEffect(() => { try { localStorage.setItem("panelWidth", String(panelW)); } catch {} }, [panelW]);
  // Light / dark theme: remembered in this browser, else follows the system setting
  const [theme, setTheme] = useState(() => {
    try { const t = localStorage.getItem("theme"); if (t === "light" || t === "dark") return t; } catch {}
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch {}
  }, [theme]);

  // Browser full screen for the whole app (Esc exits)
  const toggleFullscreen = () =>
    document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.();

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

  // at/atMw/atName let the example buttons screen right away (state updates aren't visible yet)
  async function runScreen(at = pin, atMw = mw, atName = name) {
    setLoading(true);
    setError("");
    setSelectedId(null);
    setAlts(null);
    try {
      const r = await screenSite(at.lat, at.lon, Number(atMw), atName, withPopulation, radius);
      setResult(r);
      loadBriefs(r);   // results show now; the AI briefs fill in when ready
    } catch (e) {
      setError(e.message);
      setResult(null);
    }
    setLoading(false);
  }

  // Briefs are written after the results appear (Gemini can take several seconds)
  function loadBriefs(r) {
    if (!r || r.briefs || !r.screening_id) return;
    const same = (cur) => cur && cur.screening_id === r.screening_id;
    fetchBriefs(r.screening_id)
      .then((b) => setResult((cur) => (same(cur) ? { ...cur, briefs: b } : cur)))
      .catch(() => setResult((cur) => (same(cur) ? { ...cur, briefs: { error: true } } : cur)));
  }

  // Example buttons: place the pin and screen in one click
  function tryExample(ex) {
    if (ex.project) {
      openProject(ex.project);
      return runScreen({ lat: ex.project.lat, lon: ex.project.lon }, ex.project.mw || 100, ex.project.name);
    }
    dropPin(ex);
    setMw(ex.mw);
    runScreen(ex, ex.mw, "");
  }
  const nyExample = projects.find((p) => p.source === "nyiso" && /^Planned/.test(p.status || ""));

  // Rotating progress text while screening
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!loading) return setStep(0);
    const t = setInterval(() => setStep((i) => Math.min(i + 1, STEPS.length - 1)), 1800);
    return () => clearInterval(t);
  }, [loading]);

  function openAlert(a) {
    openProject({ name: a.name, lat: a.lat, lon: a.lon, mw: a.mw, county: a.county, state: "NY",
      source: "nyiso", approximate: 1, notes: a.summary });
    setResult(a.result);
    loadBriefs(a.result);
  }

  return (
    <div className="flex h-full flex-col bg-slate-50 text-slate-800">
      {/* Keyboard users can jump past the header (WCAG 2.4.1) */}
      <a href="#panel" className="sr-only rounded-md bg-emerald-600 px-3 py-2 text-white focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50">
        Skip to the screening panel
      </a>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b bg-white px-5 py-3">
        <h1 className="text-lg font-bold">
          Before the <span className="text-emerald-600">Build</span>
          <span className="ml-3 hidden text-sm font-normal text-slate-500 lg:inline">What's on this land before a data center is built?</span>
        </h1>
        <nav className="flex flex-wrap gap-1" aria-label="Main">
          {["screen", "alerts"].map((t) => (
            <button key={t} onClick={() => setTab(t)} aria-pressed={tab === t}
              className={`rounded-md px-3 py-1.5 text-sm ${tab === t ? "bg-slate-800 text-white" : "hover:bg-slate-100"}`}>
              {t === "screen" ? "Screen a site" : "Alerts"}
            </button>
          ))}
          <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-pressed={theme === "dark"}
            title="Switch light / dark theme" className="rounded-md px-3 py-1.5 text-sm hover:bg-slate-100">
            {/* Sun (Melonade) in dark mode, moon (Royal Seal) in light mode; ︎ keeps them as text, not emoji */}
            <span aria-hidden="true" className="text-base leading-none text-emerald-600">{theme === "dark" ? "☀︎" : "☾︎"}</span>
            {" "}{theme === "dark" ? "Light" : "Dark"} theme
          </button>
          <button onClick={() => setMapOnly(!mapOnly)} title="Hide or show the side panel" aria-pressed={mapOnly}
            className="rounded-md px-3 py-1.5 text-sm hover:bg-slate-100">{mapOnly ? "Show panel" : "Map only"}</button>
          <button onClick={toggleFullscreen} title="Full screen (Esc to exit)"
            className="rounded-md px-3 py-1.5 text-sm hover:bg-slate-100"><span aria-hidden="true">⛶</span> Full screen</button>
        </nav>
      </header>

      <main className="flex min-h-0 flex-1 flex-col md:flex-row">
        <aside id="panel" tabIndex={-1} aria-label="Screening panel" style={{ "--panel-w": `${panelW}px` }}
          className={`${mapOnly ? "hidden" : ""} order-2 max-h-[55vh] w-full shrink-0 overflow-y-auto border-t bg-white p-5 md:order-1 md:max-h-none md:w-[var(--panel-w)] md:max-w-[calc(100vw-320px)] md:border-t-0`}>
          {tab === "alerts" ? (
            <ErrorBoundary><Alerts onOpen={openAlert} /></ErrorBoundary>
          ) : (
            <>
              <div className="space-y-3">
                <Search projects={projects} onProject={openProject} onPlace={dropPin} />

                {!pin && (
                  <div className="rounded-xl border bg-slate-50 p-4 shadow-sm">
                    <h2 className="text-base font-semibold">See what's on the land before a data center is built.</h2>
                    <p className="mt-1 text-sm text-slate-600">
                      Wetlands, flood zones, protected land, nearby homes, likely permits, and the water and power it would use,
                      with a plain-language brief for neighbors and developers.
                    </p>
                    <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Try an example</div>
                    <div className="mt-1 grid gap-2">
                      {[...EXAMPLES, ...(nyExample ? [{ label: "NY grid queue project", where: nyExample.county ? `${nyExample.county} County, NY` : "New York", project: nyExample }] : [])]
                        .map((ex) => (
                          <button key={ex.label} onClick={() => tryExample(ex)} disabled={loading}
                            className="rounded-lg border bg-white px-3 py-2 text-left text-sm shadow-sm hover:border-emerald-300 hover:bg-emerald-50 disabled:opacity-50">
                            <span className="font-medium">{ex.label}</span>
                            <span className="ml-2 text-xs text-slate-500">{ex.where}</span>
                          </button>
                        ))}
                    </div>
                    <p className="mt-3 text-xs text-slate-500">
                      Or click a <b className="text-violet-600">project pin</b> on the map, search an address, or click anywhere in the US.
                    </p>
                  </div>
                )}
                {loading && !pin && <p role="status" className="text-sm text-slate-600">{STEPS[step]}</p>}

                {pin && (project ? <ProjectCard p={project} /> : (
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
                    <div className="font-medium text-emerald-800">New proposed data center</div>
                    <div className="text-xs text-emerald-700">Pin: {pin.lat.toFixed(4)}, {pin.lon.toFixed(4)}</div>
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project / company name (optional)"
                      aria-label="Project or company name (optional)"
                      className="mt-2 w-full rounded-md border bg-white px-2 py-1" />
                  </div>
                ))}

                {pin && (
                  <>
                    <label className="flex items-center gap-2 text-sm">
                      Planned capacity
                      <input type="number" min="1" value={mw} onChange={(e) => setMw(e.target.value)}
                        className="w-24 rounded-md border px-2 py-1" /> <Term k="MW">MW</Term>
                    </label>
                    <label className="block text-sm">
                      <span className="flex justify-between">
                        <span>Search radius</span>
                        <span className="font-medium tabular-nums">{radius} km</span>
                      </span>
                      <input type="range" min="5" max="100" step="5" value={radius}
                        onChange={(e) => setRadius(Number(e.target.value))} className="w-full accent-emerald-600" />
                      {radius > 5 && <span className="text-xs text-slate-500">
                        Exact distances within 5 km; beyond that, how far the nearest one is. Lower-risk spot search also goes out to {radius} km (slower).
                      </span>}
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input type="checkbox" checked={withPopulation} onChange={(e) => setWithPopulation(e.target.checked)} />
                      Include population nearby (2020 Census, slower)
                    </label>
                    <button onClick={() => runScreen()} disabled={loading} aria-busy={loading}
                      className="w-full rounded-md bg-emerald-600 py-2 font-medium text-white hover:bg-emerald-700 disabled:opacity-40">
                      {loading ? STEPS[step] : "Screen site"}
                    </button>
                  </>
                )}
                {error && <p role="alert" className="rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
              </div>
              <p className="sr-only" role="status" aria-live="polite">
                {loading ? "Screening the site, please wait." : result ? `Screening done: ${result.triggers.length} likely review triggers.` : ""}
              </p>
              {result && (
                <ErrorBoundary>
                  <Results result={result} selectedId={selectedId} onSelect={setSelectedId} />
                  <Alternatives key={`${result.site.lat},${result.site.lon},${result.site.mw}`} result={result}
                    onFound={setAlts} onGo={(c) => dropPin({ lat: c.lat, lon: c.lon })} />
                </ErrorBoundary>
              )}
            </>
          )}
        </aside>
        {!mapOnly && <PanelResizer width={panelW} onResize={setPanelW} />}
        <section className="relative order-1 min-h-[45vh] min-w-0 flex-1 md:order-3" aria-label="Map">
          <ErrorBoundary>
            <MapView pin={pin} projects={projects} onPick={(lat, lon) => dropPin({ lat, lon })} onProject={openProject}
              result={result} selectedId={selectedId} onSelect={setSelectedId} alts={alts} theme={theme} />
          </ErrorBoundary>
        </section>
      </main>

      <footer className="flex justify-between gap-4 border-t bg-white px-5 py-1.5 text-xs text-slate-500">
        <span>Screening-level only, from public GIS data. Not a site survey. Does not predict permit outcomes.</span>
        <span aria-hidden="true"><Fps /></span>
      </footer>
    </div>
  );
}

// Divider between the side panel and the map: drag to resize, arrow keys to nudge, double-click to reset.
// Side-by-side layout only (md and up); on narrow screens the panel sits under the map.
function PanelResizer({ width, onResize }) {
  function startDrag(e) {
    e.preventDefault();
    const handle = e.currentTarget;
    const left = handle.previousElementSibling.getBoundingClientRect().left;
    handle.setPointerCapture(e.pointerId);
    document.body.style.userSelect = "none";
    const move = (ev) => onResize(clampPanel(ev.clientX - left));
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
      handle.removeEventListener("pointercancel", stop);
      document.body.style.userSelect = "";
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
  }
  function onKey(e) {
    const step = e.shiftKey ? 80 : 20;
    if (e.key === "ArrowLeft") onResize(clampPanel(width - step));
    else if (e.key === "ArrowRight") onResize(clampPanel(width + step));
    else if (e.key === "Home") onResize(clampPanel(PANEL_MIN));
    else return;
    e.preventDefault();
  }
  return (
    <div role="separator" aria-orientation="vertical" aria-label="Resize side panel"
      aria-valuenow={width} aria-valuemin={PANEL_MIN} tabIndex={0}
      title="Drag to resize the panel (double-click to reset)"
      onPointerDown={startDrag} onKeyDown={onKey} onDoubleClick={() => onResize(clampPanel(PANEL_DEFAULT))}
      className="group relative z-10 hidden w-1.5 shrink-0 cursor-col-resize touch-none border-r bg-white hover:bg-emerald-200 focus-visible:bg-emerald-200 md:order-2 md:block">
      {/* grip dots */}
      <span aria-hidden="true" className="absolute top-1/2 left-1/2 h-8 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded bg-slate-300 group-hover:bg-emerald-600" />
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
