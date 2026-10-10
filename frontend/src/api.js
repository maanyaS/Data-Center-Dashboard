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

export const screenSite = (lat, lon, mw) => post("/screen", { lat, lon, mw }).then((r) => r.json());
export const getDemoSites = () => call("/demo-sites").then((r) => r.json());
export const getAlerts = () => call("/alerts").then((r) => r.json());
export const speak = (text) => post("/voice", { text }).then((r) => r.blob());
