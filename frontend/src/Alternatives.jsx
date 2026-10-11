import { useState } from "react";
import { findAlternatives } from "./api";

// "Find a lower-risk spot nearby" + side-by-side comparison with the original site.
const fmtM = (m, c) => c?.checked_km
  ? (m == null ? `>${c.checked_km} km` : m === 0 ? "inside" : m <= 200 ? "≤200 m" : "≤1 km")
  : m == null ? "None" : m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m} m`;
const ROWS_FIRST = ["fema_flood", "nj_wetlands", "nwi_wetlands", "ny_wetlands", "de_wetlands",
  "protected_areas", "nj_open_space", "ny_protected", "nj_highlands", "nj_pinelands", "nj_cafra", "critical_habitat"];

// For power lines and substations, closer is GOOD (cheaper, faster grid connection)
const CLOSER_IS_BETTER = ["transmission_lines", "substations"];

function cellClass(m, layer) {
  if (CLOSER_IS_BETTER.includes(layer)) {
    if (m == null) return "font-semibold text-red-700";
    return m <= 2000 ? "text-emerald-700" : "text-amber-700";
  }
  if (m == null) return "text-emerald-700";
  if (m <= 200) return "font-semibold text-red-700";
  if (m <= 1000) return "text-amber-700";
  return "text-slate-600";
}

export default function Alternatives({ result, onFound, onGo }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { site } = result;
  const radius = site.radius_km || 5;

  async function run() {
    setLoading(true);
    setError("");
    try {
      const d = await findAlternatives(site.lat, site.lon, Number(site.mw) || 100, radius);
      setData(d);
      onFound(d.candidates);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  }

  if (!data) {
    return (
      <div className="mt-6 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm">
        <div className="font-medium text-sky-900">Is there a lower-risk spot nearby?</div>
        <p className="mt-1 text-xs text-sky-800">
          {radius > 5
            ? `Tests 40 points: 24 within 2.5 km plus 16 at ${radius / 2} and ${radius} km (far spots take ~10-20 s)`
            : "Tests 24 points within 2.5 km"} using the same layers and rules, then compares the best ones to this site.
        </p>
        <button onClick={run} disabled={loading}
          className="mt-2 w-full rounded-md bg-sky-600 py-1.5 font-medium text-white hover:bg-sky-700 disabled:opacity-40">
          {loading ? "Testing nearby spots…" : "Find a lower-risk spot nearby"}
        </button>
        {error && <p className="mt-2 rounded-md bg-red-50 p-2 text-red-700">{error}</p>}
      </div>
    );
  }

  const cols = [data.origin, ...data.candidates];
  const maxScore = Math.max(1, ...cols.map((c) => c.score));
  const all = Object.keys(data.origin.titles).filter((l) => l in data.origin.nearest);
  // Rows where nothing is within 5 km at ANY spot are collapsed into one line
  const empty = all.filter((l) => !CLOSER_IS_BETTER.includes(l) && cols.every((c) => c.nearest[l] == null && !c.checked_km));
  const layers = all.filter((l) => !empty.includes(l))
    .sort((a, b) => (ROWS_FIRST.indexOf(a) + 1 || 99) - (ROWS_FIRST.indexOf(b) + 1 || 99));

  return (
    <div className="mt-6 space-y-3 rounded-lg border border-sky-200 bg-white p-3 text-sm">
      <div className="font-semibold text-sky-900">Lower-risk spots nearby</div>
      <p className="text-xs text-slate-600">{data.message}</p>

      {/* Score bars: the quick visual */}
      <div className="space-y-1.5">
        {cols.map((c, i) => (
          <div key={c.label} className="flex items-center gap-2 text-xs">
            <span className={`w-24 shrink-0 ${i === 0 ? "font-semibold" : ""}`}>
              {i === 0 ? "Original" : `#${i} · ${c.label}`}
            </span>
            <div className="h-3 flex-1 rounded bg-slate-100">
              <div className={`h-3 rounded ${i === 0 ? "bg-slate-500" : "bg-sky-500"}`}
                style={{ width: `${(c.score / maxScore) * 100}%` }} />
            </div>
            <span className="w-28 shrink-0 text-right tabular-nums">
              score {c.score} · {c.high} high
            </span>
          </div>
        ))}
      </div>

      {/* Side-by-side table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-left text-slate-500">
              <th scope="col" className="py-1 pr-2 font-medium">Nearest…</th>
              {cols.map((c, i) => (
                <th scope="col" key={c.label} className="py-1 pr-2 font-medium">{i === 0 ? "Original" : `#${i}`}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {layers.map((l) => (
              <tr key={l} className="border-b border-slate-100">
                <td className="py-1 pr-2 text-slate-600">{data.origin.titles[l]}</td>
                {cols.map((c) => (
                  <td key={c.label} className={`py-1 pr-2 tabular-nums ${cellClass(c.nearest[l], l)}`}>{fmtM(c.nearest[l], c)}</td>
                ))}
              </tr>
            ))}
            {cols.some((c) => c.people_1km != null) && (
              <tr className="border-b border-slate-100">
                <td className="py-1 pr-2 text-slate-600">People within 1 km (2020 Census)</td>
                {cols.map((c) => (
                  <td key={c.label} className="py-1 pr-2 tabular-nums">{c.people_1km == null ? "unknown" : c.people_1km.toLocaleString()}</td>
                ))}
              </tr>
            )}
            <tr className="border-b border-slate-100">
              <td className="py-1 pr-2 text-slate-600">Water stress</td>
              {cols.map((c) => <td key={c.label} className="py-1 pr-2">{c.water_stress || "unknown"}</td>)}
            </tr>
            <tr>
              <td className="py-1 pr-2 text-slate-600">Review triggers</td>
              {cols.map((c) => (
                <td key={c.label} className="py-1 pr-2 align-top">
                  {c.triggers.map((t) => (
                    <span key={t.rule_id} title={t.trigger}
                      className={`mr-1 inline-block rounded px-1 ${t.delay_risk === "high" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
                      {t.rule_id}
                    </span>
                  ))}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {empty.length > 0 && (
        <p className="text-xs text-emerald-700">
          None within 5 km of any spot: {empty.map((l) => data.origin.titles[l]).join(", ")}.
        </p>
      )}

      {data.candidates.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {data.candidates.map((c, i) => (
            <button key={c.label} onClick={() => onGo(c)}
              className="rounded-md border border-sky-300 px-2 py-1 text-xs text-sky-800 hover:bg-sky-50">
              Move pin to #{i + 1} ({c.label})
            </button>
          ))}
        </div>
      )}

      <p className="text-xs leading-snug text-slate-500">
        {data.caveat} {data.scoring}
        {data.unchecked_layers.length > 0 && ` Not checked: ${data.unchecked_layers.join(", ")}.`}
      </p>
    </div>
  );
}
