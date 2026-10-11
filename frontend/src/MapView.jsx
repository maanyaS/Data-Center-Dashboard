import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { getOverlay, getTracts } from "./api";

// Basemap: Geoapify if VITE_GEOAPIFY_KEY is set (frontend/.env), else free CARTO Positron
const GEOAPIFY_KEY = import.meta.env.VITE_GEOAPIFY_KEY;
const STYLE = GEOAPIFY_KEY
  ? `https://maps.geoapify.com/v1/styles/positron/style.json?apiKey=${GEOAPIFY_KEY}`
  : "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const EMPTY = { type: "FeatureCollection", features: [] };

// Map overlays (same 0-4 level scale, low -> high)
const LEVEL_COLORS = ["#fef9c3", "#fde68a", "#fb923c", "#ef4444", "#7f1d1d"];
const OVERLAYS = {
  water_stress: { title: "Water stress (WRI Aqueduct 4.0)", labels: ["Low", "Low-Med", "Med-High", "High", "Extremely high"] },
  climate_risk: { title: "Climate risk (FEMA National Risk Index)", labels: ["Very low", "Rel. low", "Rel. moderate", "Rel. high", "Very high"] },
};
// Population density has its own purple scale so it can sit on top of water stress / climate risk
const POP_COLORS = ["#f3e8ff", "#d8b4fe", "#a855f7", "#7e22ce", "#3b0764"];
const POP_LABELS = ["Under 100", "100–500", "500–1,500", "1,500–4,000", "4,000+"];
// Census-tract detail for population is added on top once the view is this small (degrees)
const TRACT_MAX_DEG = 1.0;

// Bounds of any GeoJSON geometry -> [[minLon, minLat], [maxLon, maxLat]]
function bounds(geometry) {
  const b = [[180, 90], [-180, -90]];
  const walk = (c) => {
    if (typeof c[0] === "number") {
      b[0][0] = Math.min(b[0][0], c[0]); b[0][1] = Math.min(b[0][1], c[1]);
      b[1][0] = Math.max(b[1][0], c[0]); b[1][1] = Math.max(b[1][1], c[1]);
    } else c.forEach(walk);
  };
  walk(geometry.coordinates);
  return b;
}

// Whole-US overlays: each is downloaded once, kept in memory, and stays on the map while panning/zooming
const national = {};
const wanted = {}; // sourceId -> overlay name currently switched on
function loadOverlay(m, name, sourceId = "overlay") {
  const src = m?.getSource(sourceId);
  if (!src) return;
  wanted[sourceId] = name;
  if (!name) return src.setData(EMPTY);
  national[name] ??= getOverlay(name).catch((e) => { delete national[name]; throw e; });
  national[name].then((g) => { if (wanted[sourceId] === name) src.setData(g); }).catch(() => {});
}

// Zoomed-in population detail (Census tracts for the current view); a newer request cancels the older one
let tractReq;
function loadTracts(m, on) {
  const src = m?.getSource("population-detail");
  if (!src) return;
  tractReq?.abort();
  const b = m.getBounds();
  if (!on || b.getEast() - b.getWest() > TRACT_MAX_DEG || b.getNorth() - b.getSouth() > TRACT_MAX_DEG) {
    return src.setData(EMPTY);
  }
  const ctrl = (tractReq = new AbortController());
  getTracts([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((x) => x.toFixed(3)).join(","), ctrl.signal)
    .then((g) => { if (!ctrl.signal.aborted) src.setData(g); })
    .catch(() => {});
}

// Existing projects -> GeoJSON points for the map
const projectsGeojson = (projects) => ({
  type: "FeatureCollection",
  features: projects.map((p) => ({
    type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    properties: { id: p.id, name: p.name, source: p.source, mw: p.mw },
  })),
});

export default function MapView({ pin, projects, onPick, onProject, result, selectedId, onSelect, alts }) {
  const box = useRef(null);
  const map = useRef(null);
  const marker = useRef(null);
  const altMarkers = useRef([]);
  const handlers = useRef({});
  const [overlay, setOverlay] = useState(""); // "", "water_stress", "climate_risk"
  const [wildlife, setWildlife] = useState(false);
  const [population, setPopulation] = useState(false);
  handlers.current = { onPick, onSelect, onProject, projects, overlay, wildlife, population };

  // Lower-risk candidates from "Find a lower-risk spot nearby" (numbered blue pins)
  useEffect(() => {
    altMarkers.current.forEach((mk) => mk.remove());
    altMarkers.current = [];
    if (!map.current || !alts) return;
    alts.forEach((c, i) => {
      const el = document.createElement("div");
      el.textContent = String(i + 1);
      el.title = `#${i + 1} ${c.label} - score ${c.score}`;
      el.style.cssText = "width:22px;height:22px;border-radius:50%;background:#0284c7;color:#fff;font:600 12px sans-serif;" +
        "display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)";
      altMarkers.current.push(new maplibregl.Marker({ element: el }).setLngLat([c.lon, c.lat]).addTo(map.current));
    });
  }, [alts]);

  // Create the map once
  useEffect(() => {
    const m = new maplibregl.Map({ container: box.current, style: STYLE, center: [-96, 38.5], zoom: 3.6 });
    map.current = m;
    // The pin can be dragged to a new spot
    marker.current = new maplibregl.Marker({ color: "#059669", draggable: true });
    marker.current.on("dragend", () => {
      const p = marker.current.getLngLat();
      handlers.current.onPick(p.lat, p.lng);
    });
    m.on("load", () => {
      m.addSource("overlay", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "overlay", type: "fill", source: "overlay",
        paint: { "fill-color": ["match", ["get", "level"], ...LEVEL_COLORS.flatMap((c, i) => [i, c]), "#ccc"],
          "fill-opacity": 0.45, "fill-outline-color": "#ffffff" } });
      m.addSource("population", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "population", type: "fill", source: "population",
        paint: { "fill-color": ["match", ["get", "level"], ...POP_COLORS.flatMap((c, i) => [i, c]), "#ccc"],
          "fill-opacity": 0.5, "fill-outline-color": "#ffffff" } });
      m.addSource("population-detail", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "population-detail", type: "fill", source: "population-detail",
        paint: { "fill-color": ["match", ["get", "level"], ...POP_COLORS.flatMap((c, i) => [i, c]), "#ccc"],
          "fill-opacity": 0.4, "fill-outline-color": "#ffffff" } });
      m.addSource("wildlife", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "wildlife", type: "fill", source: "wildlife",
        paint: { "fill-color": "#16a34a", "fill-opacity": 0.3, "fill-outline-color": "#15803d" } });
      m.addSource("rings", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "rings", type: "line", source: "rings",
        paint: { "line-color": "#334155", "line-dasharray": [2, 2], "line-width": 1.5 } });
      // Distance labels along each ring
      m.addLayer({ id: "ring-labels", type: "symbol", source: "rings",
        layout: { "symbol-placement": "line", "symbol-spacing": 250, "text-size": 12,
          "text-font": ["Open Sans Bold"],
          "text-field": ["match", ["get", "ring"], "site", "200 m", "1km", "1 km", "5km", "5 km", ""] },
        paint: { "text-color": "#1e293b", "text-halo-color": "#ffffff", "text-halo-width": 2 } });
      m.addSource("findings", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "findings-fill", type: "fill", source: "findings",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": ["get", "color"],
          "fill-opacity": ["case", ["get", "selected"], 0.6, 0.25] } });
      // Point findings (e.g. substations) as circles
      m.addLayer({ id: "findings-point", type: "circle", source: "findings",
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-color": ["get", "color"], "circle-radius": ["case", ["get", "selected"], 8, 5],
          "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
      m.addLayer({ id: "findings-line", type: "line", source: "findings",
        paint: { "line-color": ["get", "color"],
          "line-width": ["case", ["get", "selected"], 3, 1] } });
      m.addSource("projects", { type: "geojson", data: projectsGeojson(handlers.current.projects) });
      m.addLayer({ id: "projects", type: "circle", source: "projects",
        paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 4, 12, 8],
          "circle-color": ["match", ["get", "source"], "nyiso", "#f97316", "#7c3aed"],
          "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
      // Hover: show project name
      const tip = new maplibregl.Popup({ closeButton: false, offset: 10 });
      m.on("mouseenter", "projects", (e) => {
        m.getCanvas().style.cursor = "pointer";
        const f = e.features[0].properties;
        tip.setLngLat(e.lngLat).setText(`${f.name} · ${f.mw} MW`).addTo(m);
      });
      m.on("mouseleave", "projects", () => { m.getCanvas().style.cursor = ""; tip.remove(); });
      m.on("mousemove", "wildlife", (e) => {
        if (m.queryRenderedFeatures(e.point, { layers: ["projects"] }).length) return;
        tip.setLngLat(e.lngLat).setText(e.features[0].properties.label || "Wildlife area").addTo(m);
      });
      m.on("mouseleave", "wildlife", () => tip.remove());
      // Population: show people + density on hover (county or tract)
      for (const id of ["population", "population-detail"]) {
        m.on("mousemove", id, (e) => {
          if (m.queryRenderedFeatures(e.point, { layers: ["projects", "wildlife"] }).length) return;
          if (id === "population" && m.queryRenderedFeatures(e.point, { layers: ["population-detail"] }).length) return;
          tip.setLngLat(e.lngLat).setText(e.features[0].properties.label).addTo(m);
        });
        m.on("mouseleave", id, () => tip.remove());
      }
    });
    // National overlays stay put; only the zoomed-in tract detail reloads after moving (debounced)
    let moveTimer;
    m.on("moveend", () => {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(() => loadTracts(m, handlers.current.population), 300);
    });
    m.on("click", (e) => {
      const proj = m.queryRenderedFeatures(e.point, { layers: ["projects"] })[0];
      if (proj) return handlers.current.onProject(handlers.current.projects.find((p) => p.id === proj.properties.id));
      const hit = m.queryRenderedFeatures(e.point, { layers: ["findings-fill", "findings-line"] })[0];
      if (hit) handlers.current.onSelect(hit.properties.id);
      else handlers.current.onPick(e.lngLat.lat, e.lngLat.lng);
    });
    return () => m.remove();
  }, []);

  // Pin marker
  useEffect(() => {
    if (!pin) return;
    marker.current.setLngLat([pin.lon, pin.lat]).addTo(map.current);
    map.current.flyTo({ center: [pin.lon, pin.lat], zoom: Math.max(map.current.getZoom(), 12) });
  }, [pin]);

  // Overlays: whole country, downloaded once when first switched on
  useEffect(() => { loadOverlay(map.current, overlay); }, [overlay]);
  useEffect(() => { loadOverlay(map.current, wildlife && "wildlife_areas", "wildlife"); }, [wildlife]);
  useEffect(() => {
    loadOverlay(map.current, population && "population", "population");
    loadTracts(map.current, population);
  }, [population]);

  // Drop the "drag pin" chip onto the map -> new pin at that spot
  function onDrop(e) {
    e.preventDefault();
    const r = box.current.getBoundingClientRect();
    const p = map.current.unproject([e.clientX - r.left, e.clientY - r.top]);
    onPick(p.lat, p.lng);
  }

  // Project pins (data arrives after the map may already be loaded)
  useEffect(() => {
    map.current.getSource("projects")?.setData(projectsGeojson(projects));
  }, [projects]);

  // Rings + finding features
  useEffect(() => {
    const m = map.current;
    const draw = () => {
      m.getSource("rings").setData(result?.rings || EMPTY);
      m.getSource("findings").setData({
        type: "FeatureCollection",
        features: (result?.findings || []).filter((f) => f.geometry).map((f) => ({
          type: "Feature", geometry: f.geometry,
          properties: { id: f.id, color: f.color, selected: f.id === selectedId },
        })),
      });
    };
    m.getSource("rings") ? draw() : m.once("load", draw);
  }, [result, selectedId]);

  // Zoom to the selected finding
  useEffect(() => {
    const f = result?.findings.find((x) => x.id === selectedId);
    if (f?.geometry) map.current.fitBounds(bounds(f.geometry), { padding: 80, maxZoom: 16 });
  }, [selectedId]);

  const legend = (result?.findings || []).filter((f) => f.geometry);
  return (
    <>
      <div ref={box} style={{ position: "absolute", inset: 0 }}
        onDragOver={(e) => e.preventDefault()} onDrop={onDrop} />
      <div className="absolute top-3 left-3 rounded-md bg-white/95 px-3 py-2 text-xs shadow">
        <div className="flex items-center gap-2"><Dot c="#7c3aed" /> Known project (FracTracker / NJ list)</div>
        <div className="flex items-center gap-2"><Dot c="#f97316" /> NYISO queue (approx. county location)</div>
        <div className="flex items-center gap-2"><Dot c="#059669" /> Your pin (drag to move)</div>
        <div draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", "pin")}
          title="Drag onto the map to place a pin"
          className="mt-2 cursor-grab rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-center font-medium text-emerald-700 active:cursor-grabbing">
          📍 Drag a pin onto the map
        </div>
      </div>
      <div className="absolute top-3 right-3 w-56 rounded-md bg-white/95 p-2 text-xs shadow">
        <div className="mb-1 font-semibold text-slate-600">Map overlay</div>
        {[["", "None"], ["water_stress", "Water stress"], ["climate_risk", "Climate risk"]].map(([k, label]) => (
          <label key={k} className="flex cursor-pointer items-center gap-2 py-0.5">
            <input type="radio" name="overlay" checked={overlay === k} onChange={() => setOverlay(k)} /> {label}
          </label>
        ))}
        <label className="mt-1 flex cursor-pointer items-center gap-2 border-t pt-1.5">
          <input type="checkbox" checked={wildlife} onChange={(e) => setWildlife(e.target.checked)} />
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: "#16a34a", opacity: 0.6 }} />
          Wildlife refuges & habitat
        </label>
        {wildlife && <div className="pl-5 text-slate-400">PAD-US refuges &amp; habitat areas, whole US</div>}
        <label className="flex cursor-pointer items-center gap-2 pt-1">
          <input type="checkbox" checked={population} onChange={(e) => setPopulation(e.target.checked)} />
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: POP_COLORS[3], opacity: 0.6 }} />
          Population density
        </label>
        {population && (
          <div className="pl-5">
            {POP_LABELS.map((l, i) => (
              <div key={l} className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: POP_COLORS[i] }} /> {l} /km²
              </div>
            ))}
            <div className="text-slate-400">2020 Census · counties, tracts when zoomed in</div>
          </div>
        )}
        {overlay && (
          <div className="mt-2 border-t pt-2">
            <div className="mb-1 text-slate-500">{OVERLAYS[overlay].title}</div>
            {OVERLAYS[overlay].labels.map((l, i) => (
              <div key={l} className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: LEVEL_COLORS[i] }} /> {l}
              </div>
            ))}
            {OVERLAYS[overlay].note && <div className="mt-1 text-slate-400">{OVERLAYS[overlay].note}</div>}
          </div>
        )}
      </div>
      {legend.length > 0 && (
        <div className="absolute bottom-4 right-4 rounded-md bg-white/95 p-3 text-xs shadow">
          {legend.map((f) => (
            <div key={f.id} className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ background: f.color }} />
              {f.title}
            </div>
          ))}
          <div className="mt-1 text-slate-500">Dashed rings: 200 m · 1 km · 5 km</div>
        </div>
      )}
    </>
  );
}

const Dot = ({ c }) => <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} />;
