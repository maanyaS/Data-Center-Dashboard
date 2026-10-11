import { useRef, useState } from "react";
import { speak } from "./api";

const RISK = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};
const BUFFER = { site: "At site", "1km": "Within 1 km", "5km": "Within 5 km", none: "None within 5 km", unknown: "Unknown" };
const num = (n) => n.toLocaleString();
const compact = (n) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
// "None within 5 km", or with a wider search: "10–25 km away" / "None within 50 km"
const bufferLabel = (f) => f.far ? `${f.far.min_km}–${f.far.max_km} km away`
  : f.none_within_km ? `None within ${f.none_within_km} km` : BUFFER[f.buffer];
const fmtM = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m} m`);
const PROTECTED = ["protected_areas", "nj_open_space", "critical_habitat"];

// Small line icons per kind of finding (drawn in the finding's map color)
const ICONS = {
  water: "M12 3s-6 7-6 11a6 6 0 0 0 12 0c0-4-6-11-6-11z",
  flood: "M2 10c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2M2 16c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2",
  power: "M13 2 4 14h7l-1 8 9-12h-7z",
  people: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM5 21a7 7 0 0 1 14 0",
  hazard: "M12 3l9 16H3zM12 10v4M12 17h.01",
  land: "M5 19C5 11 11 5 19 5c0 8-6 14-14 14zM5 19l7-7",
};
const kind = (layer) => /flood|cafra/.test(layer) ? "flood" : /wetland|water/.test(layer) ? "water"
  : /transmission|substation/.test(layer) ? "power" : /census|population/.test(layer) ? "people"
  : /climate/.test(layer) ? "hazard" : "land";
export const Icon = ({ layer, color }) => (
  <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke={color || "currentColor"}
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={ICONS[kind(layer)]} />
  </svg>
);

export default function Results({ result, selectedId, onSelect }) {
  const { findings, triggers, estimates, briefs } = result;

  return (
    <div className="mt-6 space-y-6">
      <Summary result={result} />

      {estimates.carbon && <CarbonCard c={estimates.carbon} />}

      {/* The conclusion first; the evidence below */}
      {!briefs ? (
        <Section title="Brief">
          <p role="status" className="animate-pulse text-sm text-slate-500">Writing the brief…</p>
        </Section>
      ) : briefs.error ? (
        <Section title="Brief">
          <p className="text-sm text-slate-500">The brief could not be written right now. Re-run the screening to try again.</p>
        </Section>
      ) : (
        <Briefs briefs={briefs} onSelect={onSelect} />
      )}

      <Section title="Likely review triggers">
        {triggers.length === 0 && <p className="text-sm text-slate-500">None flagged from the layers checked.</p>}
        {triggers.map((t) => (
          <div key={t.rule_id} className="rounded-xl border bg-white p-3 text-sm shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <p>{t.trigger}</p>
              <Badge risk={t.delay_risk} />
            </div>
            <p className="mt-1 text-xs text-slate-500">{t.citation}</p>
            {t.finding_ids.length > 0 && (
              <p className="mt-1 text-xs">Based on {t.finding_ids.map((id) => (
                <button key={id} onClick={() => onSelect(id)} className="mr-1 font-mono text-emerald-700 underline">[{id}]</button>
              ))}</p>
            )}
          </div>
        ))}
      </Section>

      <GridAndPeople findings={findings} onSelect={onSelect} />

      <ProtectedLands findings={findings} onSelect={onSelect} />

      <Section title="Estimated demand (ranges)">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Stat label="Electricity, MWh/year" r={estimates.power_mwh_per_year} />
          <Stat label="On-site water, gal/day" r={estimates.water_gal_per_day} />
          {estimates.grid && <>
            <Stat label="CO₂, tons/year" r={estimates.co2_tons_per_year} />
            <Stat label="Electricity cost, $/year" r={estimates.power_cost_usd_per_year} />
          </>}
        </div>
        {estimates.grid && (
          <p className="text-xs text-slate-500">
            Grid: {estimates.grid.egrid_name} ({estimates.grid.co2_lb_per_mwh} lb CO₂/MWh) · {estimates.grid.price_cents_kwh}¢/kWh industrial
          </p>
        )}
        <details className="text-xs text-slate-500">
          <summary className="cursor-pointer">Assumptions & sources</summary>
          <ul className="mt-1 list-disc pl-4">{estimates.sources.map((s) => <li key={s}>{s}</li>)}</ul>
        </details>
      </Section>

      {/* Full evidence, collapsed (opens automatically when a finding is picked on the map) */}
      <details open={!!selectedId} className="group">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-500">
          All findings ({findings.length})
        </summary>
        <div className="mt-2 space-y-2">
          {findings.map((f) => (
            <button key={f.id} onClick={() => onSelect(f.id)} aria-pressed={f.id === selectedId}
              className={`w-full rounded-xl border bg-white p-3 text-left text-sm shadow-sm ${f.id === selectedId ? "ring-2 ring-emerald-500" : ""} ${f.buffer === "unknown" ? "border-dashed bg-slate-50 text-slate-500 italic" : ""}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 font-medium not-italic">
                  <Icon layer={f.layer} color={f.color} />
                  <span className="font-mono text-xs text-slate-500">{f.id}</span> {f.title}
                </span>
                <span className="text-xs whitespace-nowrap">{f.population ? "Estimate" : bufferLabel(f)}</span>
              </div>
              {f.population && (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div><div className="text-lg font-semibold">{num(f.population.within_1km)}</div><div className="text-xs text-slate-500">people within 1 km</div></div>
                  <div><div className="text-lg font-semibold">{num(f.population.within_5km)}</div><div className="text-xs text-slate-500">people within 5 km</div></div>
                </div>
              )}
              <p className="mt-1">{f.detail}</p>
            </button>
          ))}
        </div>
      </details>
    </div>
  );
}

// At-a-glance card: overall review risk + three headline numbers
function Summary({ result }) {
  const { site, triggers, estimates, findings } = result;
  const high = triggers.filter((t) => t.delay_risk === "high").length;
  const medium = triggers.filter((t) => t.delay_risk === "medium").length;
  const level = high ? ["High review risk", RISK.high] : medium ? ["Moderate review risk", RISK.medium] : ["Low review risk", RISK.low];
  const pop = findings.find((f) => f.layer === "census_tracts")?.population;
  const range = (r, unit) => `${compact(r.low)}–${compact(r.high)}${unit}`;
  return (
    <section aria-label="Screening summary" className="space-y-2">
      <div className="rounded-xl bg-slate-800 p-4 text-white shadow-sm">
        {site.name && <div className="font-medium">{site.name}</div>}
        <div className="text-sm opacity-80">{site.county}, {site.state} · {site.mw} MW</div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-3 py-1 text-sm font-semibold ${level[1]}`}>{level[0]}</span>
          <span className="text-sm">{triggers.length} likely reviews · {high} high delay</span>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <Tile icon="water" label="Water / day" value={range(estimates.water_gal_per_day, " gal")} />
        <Tile icon="hazard" label="CO₂ / year" value={estimates.co2_tons_per_year ? range(estimates.co2_tons_per_year, " t") : "unknown"} />
        <Tile icon="people" label="People ≤1 km" value={pop ? num(pop.within_1km) : "not checked"} />
      </div>
    </section>
  );
}

// Carbon impact score (0-10) for the developer, with real-world scale and ways to offset or restore
function CarbonCard({ c }) {
  const color = c.score >= 8 ? "bg-red-600" : c.score >= 6 ? "bg-red-500" : c.score >= 3 ? "bg-amber-600" : "bg-emerald-600";
  const pct = c.global_share_pct < 0.001 ? "under 0.001%" : `${c.global_share_pct.toFixed(4)}%`;
  return (
    <section aria-label="Carbon impact" className="rounded-xl border bg-white p-3 text-sm shadow-sm">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Carbon impact</h2>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${c.score >= 6 ? RISK.high : c.score >= 3 ? RISK.medium : RISK.low}`}>{c.level}</span>
      </div>
      <div className="mt-1 flex items-end gap-2">
        <span className="text-3xl font-bold tabular-nums">{c.score}</span>
        <span className="pb-1 text-slate-500">/ 10</span>
      </div>
      <div role="meter" aria-valuemin={0} aria-valuemax={10} aria-valuenow={c.score} aria-label={`Carbon impact score ${c.score} out of 10`}
        className="mt-1 h-2 rounded-full bg-slate-100">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${c.score * 10}%` }} />
      </div>
      <p className="mt-1 text-xs text-slate-500">
        {c.size_points}/6 for size of emissions + {c.grid_points}/4 for how carbon-heavy the local grid is.
      </p>
      <ul className="mt-2 space-y-0.5">
        <li>≈ <b>{num(c.tons_per_year)}</b> t CO₂ a year, like <b>{num(c.cars)}</b> cars on the road</li>
        <li>{pct} of global energy CO₂</li>
        <li className="text-xs text-slate-500">
          {c.over_reporting_threshold ? "Above" : "Below"} the EPA's 25,000 t/yr reporting threshold for comparison
          (that rule covers direct emissions; grid power counts as indirect, Scope 2).
        </li>
      </ul>
      <details className="mt-2">
        <summary className="cursor-pointer font-medium text-emerald-700">Ways to offset or restore ({c.offsets.length})</summary>
        <ul className="mt-1 space-y-1.5">
          {c.offsets.map((o) => (
            <li key={o.action} className="rounded-lg bg-slate-50 p-2">
              <div className="font-medium">{o.action}</div>
              <div className="text-xs text-slate-600">{o.amount}</div>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-slate-500">Rough estimates. Sources: {c.source}.</p>
      </details>
    </section>
  );
}

function Tile({ icon, label, value }) {
  return (
    <div className="rounded-xl border bg-white p-2.5 shadow-sm">
      <div className="flex items-center gap-1 text-xs text-slate-500"><Icon layer={icon} /> {label}</div>
      <div className="mt-0.5 font-semibold tabular-nums">{value}</div>
    </div>
  );
}

const BRIEF_PARTS = [
  ["facts", "Key facts", "border-slate-200 bg-white"],
  ["community", "Community: how to respond", "border-amber-200 bg-amber-50"],
  ["developer", "Developers: risks & next steps", "border-sky-200 bg-sky-50"],
];
// Two voices: community brief = Sarah, developer brief = George (both free-plan voices)
const LISTEN = [
  ["community", "Community brief", "Sarah", "bg-emerald-600 hover:bg-emerald-700"],
  ["developer", "Developer brief", "George", "bg-sky-600 hover:bg-sky-700"],
];
// Older saved briefs were paragraphs: show them as one bullet
const asList = (v) => (Array.isArray(v) ? v : v ? [v] : []);
const section = (briefs, k, title) => `${title}.\n${asList(briefs[k]).join("\n")}`;

function Briefs({ briefs, onSelect }) {
  const clips = useRef({});            // who -> audio URL, so replaying never calls ElevenLabs again
  const [playing, setPlaying] = useState(null); // {who, url}
  const [busy, setBusy] = useState(null);
  const [voiceErr, setVoiceErr] = useState("");
  const text = BRIEF_PARTS.filter(([k]) => briefs[k])
    .map(([k, title]) => `${title}\n${asList(briefs[k]).map((b) => `- ${b}`).join("\n")}`).join("\n\n");

  function download() {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    a.download = "before-the-build-brief.txt";
    a.click();
  }

  // Audio is only made when someone clicks (saves free-plan credits): key facts + that audience's section
  async function listen(who) {
    setVoiceErr("");
    if (clips.current[who]) return setPlaying({ who, url: clips.current[who] });
    setBusy(who);
    try {
      const spoken = `${section(briefs, "facts", "Key facts")}\n${section(briefs, who, who === "community" ? "What you can do" : "For developers")}`
        .replace(/\s*\[[A-Z]+\d*\]/g, "").slice(0, 1500);
      clips.current[who] = URL.createObjectURL(await speak(spoken, who));
      setPlaying({ who, url: clips.current[who] });
    } catch (e) { setVoiceErr(e.message); }
    setBusy(null);
  }

  // [F1] tags are clickable (highlight the finding); other tags are small and grey
  const cite = (b) => b.split(/(\[(?:F\d+|R\d+|EST|ALT\d+|ACT\d+)\])/).map((p, i) => /^\[F\d+\]$/.test(p)
    ? <button key={i} onClick={() => onSelect(p.slice(1, -1))} className="font-mono text-xs text-emerald-700 underline">{p}</button>
    : /^\[/.test(p) ? <span key={i} className="font-mono text-xs text-slate-400">{p}</span> : p);

  return (
    <Section title="Brief">
      {/* Listen: ElevenLabs voices, one per audience */}
      <div className="rounded-xl border bg-white p-3 shadow-sm">
        <div className="mb-2 text-xs font-semibold text-slate-600">Listen to the brief</div>
        <div className="grid grid-cols-2 gap-2">
          {LISTEN.map(([who, label, voice, style]) => (
            <button key={who} onClick={() => listen(who)} disabled={!!busy} aria-busy={busy === who}
              className={`rounded-lg px-3 py-2 text-left text-sm font-medium text-white disabled:opacity-60 ${style}`}>
              <span aria-hidden="true">▷</span> {busy === who ? "Preparing audio…" : label}
              <span className="block text-xs font-normal opacity-80">Voice: {voice}</span>
            </button>
          ))}
        </div>
        {playing && (
          <div className="mt-2">
            <div className="text-xs text-slate-500" role="status">
              Now playing: {playing.who === "community" ? "community" : "developer"} brief
            </div>
            <audio key={playing.url} src={playing.url} controls autoPlay className="mt-1 w-full" />
          </div>
        )}
        {voiceErr && <p role="alert" className="mt-2 text-xs text-red-700">{voiceErr}</p>}
        <p className="mt-2 text-xs text-slate-500">Voices by ElevenLabs. Audio is made only when you press play.</p>
      </div>

      {BRIEF_PARTS.filter(([k]) => briefs[k]).map(([k, title, style]) => (
        <div key={k} className={`rounded-xl border p-3 shadow-sm ${style}`}>
          <div className="mb-1 text-xs font-semibold text-slate-600">{title}</div>
          <ul className="list-disc space-y-1 pl-4 text-sm">
            {asList(briefs[k]).map((b, i) => <li key={i}>{cite(b)}</li>)}
          </ul>
        </div>
      ))}
      <div className="flex gap-2 text-sm">
        <button onClick={() => navigator.clipboard.writeText(text)} className="rounded-md border px-3 py-1">Copy</button>
        <button onClick={download} className="rounded-md border px-3 py-1">Download</button>
      </div>
      <p className="text-xs text-slate-400">
        Written {briefs.source === "llm" ? "by AI" : "from a template"} using only the findings below; every bullet cites its source.
        Screening-level only, not a site survey; does not predict permit outcomes.
      </p>
    </Section>
  );
}

// Every named protected area / open space / habitat within 5 km - for land managers
function ProtectedLands({ findings, onSelect }) {
  const layers = findings.filter((f) => PROTECTED.includes(f.layer));
  const lands = layers.flatMap((f) => (f.nearby || []).map((n) => ({ ...n, f })))
    .sort((a, b) => a.distance_m - b.distance_m);
  const unknown = layers.filter((f) => f.buffer === "unknown");
  return (
    <Section title={`Protected lands within 5 km (${lands.length})`}>
      {lands.length === 0 && <p className="text-sm text-slate-500">None found in the layers checked.</p>}
      <div className="divide-y rounded-md border text-sm">
        {lands.map((l) => (
          <button key={l.f.id + l.name} onClick={() => onSelect(l.f.id)}
            className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left hover:bg-slate-50">
            <span className="flex items-center gap-2">
              <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: l.f.color }} />
              {l.name}
            </span>
            <span className={`shrink-0 text-xs font-medium ${l.distance_m <= 200 ? "text-red-600" : l.distance_m <= 1000 ? "text-amber-600" : "text-slate-500"}`}>
              {l.distance_m === 0 ? "on site" : fmtM(l.distance_m)}
            </span>
          </button>
        ))}
      </div>
      {unknown.map((f) => <p key={f.id} className="text-xs italic text-slate-500">{f.title}: unknown (not checked)</p>)}
    </Section>
  );
}

function Section({ title, children }) {
  return (
    <section className="space-y-2">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {children}
    </section>
  );
}

function Badge({ risk }) {
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${RISK[risk] || RISK.low}`}>{risk} delay risk</span>;
}

function Stat({ label, r }) {
  return (
    <div className="rounded-xl border bg-white p-2 shadow-sm">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-semibold">{num(r.low)} – {num(r.high)}</div>
    </div>
  );
}

// Power grid access + people nearby (added). Closer power = easier connection; more people = more community impact.
function GridAndPeople({ findings, onSelect }) {
  const by = (layer) => findings.find((f) => f.layer === layer);
  const sub = by("substations"), line = by("transmission_lines"), pop = by("census_tracts");
  if (!sub && !line && !pop) return null;
  const dist = (f) => (!f || f.buffer === "unknown" ? "unknown" : f.distance_m == null ? "none within 5 km" : fmtM(f.distance_m));
  const Item = ({ f, label, value }) => (
    <button onClick={() => f && onSelect(f.id)} className="rounded-xl border bg-white p-2 text-left shadow-sm hover:bg-slate-50">
      <div className="text-xs text-slate-500">{label}{f && <span className="ml-1 font-mono">[{f.id}]</span>}</div>
      <div className="font-semibold">{value}</div>
    </button>
  );
  return (
    <div className="grid grid-cols-3 gap-2 text-sm">
      <Item f={sub} label="Nearest substation" value={dist(sub)} />
      <Item f={line} label="Nearest transmission line" value={dist(line)} />
      <Item f={pop} label="People within 1 km" value={!pop ? "not checked" : pop.population ? num(pop.population.within_1km) : "unknown"} />
    </div>
  );
}
