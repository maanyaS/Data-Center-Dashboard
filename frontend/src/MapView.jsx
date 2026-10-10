import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";

const STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const EMPTY = { type: "FeatureCollection", features: [] };

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

// Existing projects -> GeoJSON points for the map
const projectsGeojson = (projects) => ({
  type: "FeatureCollection",
  features: projects.map((p) => ({
    type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    properties: { id: p.id, name: p.name, source: p.source, mw: p.mw },
  })),
});

export default function MapView({ pin, projects, onPick, onProject, result, selectedId, onSelect }) {
  const box = useRef(null);
  const map = useRef(null);
  const marker = useRef(null);
  const handlers = useRef({});
  handlers.current = { onPick, onSelect, onProject, projects };

  // Create the map once
  useEffect(() => {
    const m = new maplibregl.Map({ container: box.current, style: STYLE, center: [-75.5, 41.8], zoom: 6 });
    map.current = m;
    marker.current = new maplibregl.Marker({ color: "#059669" });
    m.on("load", () => {
      m.addSource("rings", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "rings", type: "line", source: "rings",
        paint: { "line-color": "#334155", "line-dasharray": [2, 2], "line-width": 1.5 } });
      m.addSource("findings", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "findings-fill", type: "fill", source: "findings",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": ["get", "color"],
          "fill-opacity": ["case", ["get", "selected"], 0.6, 0.25] } });
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
      <div ref={box} style={{ position: "absolute", inset: 0 }} />
      <div className="absolute top-3 left-3 rounded-md bg-white/95 px-3 py-2 text-xs shadow">
        <div className="flex items-center gap-2"><Dot c="#7c3aed" /> Known project (NJ / NY / DE list)</div>
        <div className="flex items-center gap-2"><Dot c="#f97316" /> NYISO queue (approx. county location)</div>
        <div className="flex items-center gap-2"><Dot c="#059669" /> Your pin</div>
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
