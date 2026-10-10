// All backend calls in one place.
async function call(path, options) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res;
}

const post = (path, body) =>
  call(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const screenSite = (lat, lon, mw, name) => post("/screen", { lat, lon, mw, name }).then((r) => r.json());
export const getProjects = () => call("/projects").then((r) => r.json());
export const getAlerts = () => call("/alerts").then((r) => r.json());
export const speak = (text) => post("/voice", { text }).then((r) => r.blob());

// Place search (OpenStreetMap Nominatim), limited to the NJ + NY + DE area. Max ~1 request/second.
export async function searchPlaces(q) {
  const params = new URLSearchParams({
    q, format: "json", limit: "5", countrycodes: "us", viewbox: "-79.8,45.1,-71.8,38.4", bounded: "1",
  });
  const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
  if (!res.ok) return [];
  return (await res.json()).map((p) => ({ label: p.display_name, lat: Number(p.lat), lon: Number(p.lon) }));
}
