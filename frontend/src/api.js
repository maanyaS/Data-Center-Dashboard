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
export const getOverlay = (name, bbox) => call(`/overlay/${name}?bbox=${bbox}`).then((r) => r.json());
export const getAlerts = () => call("/alerts").then((r) => r.json());
export const speak = (text) => post("/voice", { text }).then((r) => r.blob());

const GEOAPIFY_KEY = import.meta.env.VITE_GEOAPIFY_KEY;

// US place search: Geoapify if a key is set, else OpenStreetMap Nominatim (~1 req/s).
export async function searchPlaces(q) {
  if (GEOAPIFY_KEY) {
    const params = new URLSearchParams({ text: q, filter: "countrycode:us", format: "json", limit: "5", apiKey: GEOAPIFY_KEY });
    const res = await fetch(`https://api.geoapify.com/v1/geocode/search?${params}`);
    if (!res.ok) return [];
    return (await res.json()).results.map((p) => ({ label: p.formatted, lat: p.lat, lon: p.lon }));
  }
  const params = new URLSearchParams({
    q, format: "json", limit: "5", countrycodes: "us",
  });
  const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
  if (!res.ok) return [];
  return (await res.json()).map((p) => ({ label: p.display_name, lat: Number(p.lat), lon: Number(p.lon) }));
}
