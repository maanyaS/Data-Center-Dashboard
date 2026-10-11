import { useState } from "react";
import { speak } from "./api";

const RISK = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};
const BUFFER = { site: "At site", "1km": "Within 1 km", "5km": "Within 5 km", none: "None within 5 km", unknown: "Unknown" };
const num = (n) => n.toLocaleString();
const fmtM = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m} m`);
const PROTECTED = ["protected_areas", "nj_open_space", "critical_habitat"];

export default function Results({ result, selectedId, onSelect }) {
  const { site, findings, triggers, estimates, briefs } = result;
  const high = triggers.filter((t) => t.delay_risk === "high").length;

  return (
    <div className="mt-6 space-y-6">
      <div className="rounded-lg bg-slate-800 p-3 text-sm text-white">
        {site.name && <div className="font-medium">{site.name}</div>}
        <div className="text-slate-300">{site.county}, {site.state} · {site.mw} MW</div>
        <div className="text-base font-semibold">
          {triggers.length} likely triggers · {high} high delay risk
        </div>
      </div>

      <GridAndPeople findings={findings} onSelect={onSelect} />

      <ProtectedLands findings={findings} onSelect={onSelect} />

      <Section title="Likely review triggers">
        {triggers.length === 0 && <p className="text-sm text-slate-500">None flagged from the layers checked.</p>}
        {triggers.map((t) => (
          <div key={t.rule_id} className="rounded-md border p-3 text-sm">
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

      <Section title="Findings">
        {findings.map((f) => (
          <button key={f.id} onClick={() => onSelect(f.id)}
            className={`w-full rounded-md border p-3 text-left text-sm ${f.id === selectedId ? "ring-2 ring-emerald-500" : ""} ${f.buffer === "unknown" ? "border-dashed bg-slate-50 text-slate-500 italic" : ""}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 font-medium not-italic">
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: f.color }} />
                <span className="font-mono text-xs text-slate-500">{f.id}</span> {f.title}
              </span>
              <span className="text-xs whitespace-nowrap">{f.population ? "Estimate" : BUFFER[f.buffer]}</span>
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
      </Section>

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

      <Briefs briefs={briefs} onSelect={onSelect} />
    </div>
  );
}

function Briefs({ briefs, onSelect }) {
  const [who, setWho] = useState("community");
  const [audio, setAudio] = useState(null);
  const [voiceErr, setVoiceErr] = useState("");
  const text = briefs[who];

  function download() {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    a.download = `sitecheck-${who}-brief.txt`;
    a.click();
  }

  async function listen() {
    setVoiceErr("");
    try { setAudio(URL.createObjectURL(await speak(text))); } catch (e) { setVoiceErr(e.message); }
  }

  // Make [F1] tags clickable
  const parts = text.split(/(\[(?:F\d+|R\d+|EST)\])/);

  return (
    <Section title="Briefs">
      <div className="flex gap-1">
        {["community", "developer"].map((w) => (
          <button key={w} onClick={() => { setWho(w); setAudio(null); }}
            className={`rounded-md px-3 py-1 text-sm capitalize ${who === w ? "bg-emerald-600 text-white" : "bg-slate-100"}`}>
            {w}
          </button>
        ))}
      </div>
      <p className="text-sm leading-relaxed">
        {parts.map((p, i) => /^\[F\d+\]$/.test(p)
          ? <button key={i} onClick={() => onSelect(p.slice(1, -1))} className="font-mono text-xs text-emerald-700 underline">{p}</button>
          : /^\[/.test(p) ? <span key={i} className="font-mono text-xs text-slate-400">{p}</span> : p)}
      </p>
      <div className="flex gap-2 text-sm">
        <button onClick={() => navigator.clipboard.writeText(text)} className="rounded-md border px-3 py-1">Copy</button>
        <button onClick={download} className="rounded-md border px-3 py-1">Download</button>
        <button onClick={listen} className="rounded-md border px-3 py-1">▶ Listen</button>
      </div>
      {audio && <audio src={audio} controls autoPlay className="w-full" />}
      {voiceErr && <p className="text-xs text-slate-500">{voiceErr}</p>}
      <p className="text-xs text-slate-400">Written {briefs.source === "llm" ? "by AI" : "from a template"} using only the findings above; every sentence cites its source.</p>
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
    <div className="rounded-md border p-2">
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
    <button onClick={() => f && onSelect(f.id)} className="rounded-md border p-2 text-left hover:bg-slate-50">
      <div className="text-xs text-slate-500">{label}{f && <span className="ml-1 font-mono">[{f.id}]</span>}</div>
      <div className="font-semibold">{value}</div>
    </button>
  );
  return (
    <div className="grid grid-cols-3 gap-2 text-sm">
      <Item f={sub} label="Nearest substation" value={dist(sub)} />
      <Item f={line} label="Nearest transmission line" value={dist(line)} />
      <Item f={pop} label="People within 1 km" value={pop?.population ? num(pop.population.within_1km) : "unknown"} />
    </div>
  );
}
