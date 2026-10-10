import { useState } from "react";
import { speak } from "./api";

const RISK = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};
const BUFFER = { site: "At site", "1km": "Within 1 km", "5km": "Within 5 km", none: "None within 5 km", unknown: "Unknown" };
const num = (n) => n.toLocaleString();

export default function Results({ result, selectedId, onSelect }) {
  const { site, findings, triggers, estimates, briefs } = result;
  const high = triggers.filter((t) => t.delay_risk === "high").length;

  return (
    <div className="mt-6 space-y-6">
      <div className="rounded-lg bg-slate-800 p-3 text-sm text-white">
        <div className="text-slate-300">{site.county}, {site.state} · {site.mw} MW</div>
        <div className="text-base font-semibold">
          {triggers.length} likely triggers · {high} high delay risk
        </div>
      </div>

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
              <span className="text-xs whitespace-nowrap">{BUFFER[f.buffer]}</span>
            </div>
            <p className="mt-1">{f.detail}</p>
          </button>
        ))}
      </Section>

      <Section title="Estimated demand (ranges)">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Stat label="Electricity, MWh/year" r={estimates.power_mwh_per_year} />
          <Stat label="On-site water, gal/day" r={estimates.water_gal_per_day} />
        </div>
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
