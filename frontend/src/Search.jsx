import { useState } from "react";
import { searchPlaces } from "./api";

// Search known projects by name (instant) and places by address/town (on Enter).
export default function Search({ projects, onProject, onPlace }) {
  const [q, setQ] = useState("");
  const [places, setPlaces] = useState([]);
  const [searching, setSearching] = useState(false);

  // "40.7, -74.1" -> go straight there
  const coords = q.match(/^\s*(-?\d+(\.\d+)?)\s*,\s*(-?\d+(\.\d+)?)\s*$/);
  const matches = q.length > 1
    ? projects.filter((p) => `${p.name} ${p.county}`.toLowerCase().includes(q.toLowerCase())).slice(0, 6)
    : [];

  async function submit(e) {
    e.preventDefault();
    if (coords) return pick(() => onPlace({ lat: Number(coords[1]), lon: Number(coords[3]) }));
    setSearching(true);
    setPlaces(await searchPlaces(q).catch(() => []));
    setSearching(false);
  }

  function pick(fn) {
    fn();
    setQ("");
    setPlaces([]);
  }

  return (
    <form onSubmit={submit} className="relative">
      <input value={q} onChange={(e) => { setQ(e.target.value); setPlaces([]); }}
        placeholder="Search a project, address, town, or lat, lon…"
        className="w-full rounded-md border px-3 py-2 text-sm" />
      {(matches.length > 0 || places.length > 0 || searching || (q.length > 1 && !coords)) && (
        <div className="absolute z-10 mt-1 w-full rounded-md border bg-white text-sm shadow-lg">
          {matches.map((p) => (
            <button type="button" key={p.id} onClick={() => pick(() => onProject(p))}
              className="block w-full px-3 py-2 text-left hover:bg-slate-50">
              <span className="font-medium">{p.name}</span>
              <span className="ml-2 text-xs text-slate-500">{p.county}, {p.state} · {p.mw} MW</span>
            </button>
          ))}
          {places.map((p) => (
            <button type="button" key={p.label} onClick={() => pick(() => onPlace(p))}
              className="block w-full px-3 py-2 text-left text-slate-600 hover:bg-slate-50">🖈 {p.label}</button>
          ))}
          <div className="px-3 py-1.5 text-xs text-slate-400">
            {searching ? "Searching places…" : "Press Enter to search addresses and towns"}
          </div>
        </div>
      )}
    </form>
  );
}
