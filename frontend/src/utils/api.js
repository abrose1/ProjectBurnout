/**
 * @param {string} path e.g. "/api/plants"
 * @param {Record<string, string | number | boolean | undefined | null>} [params]
 */
export function getApiBase() {
  const raw = import.meta.env.VITE_API_URL;
  if (raw == null || String(raw).trim() === "") {
    return "";
  }
  return String(raw).replace(/\/$/, "");
}

export async function apiGet(path, params = {}) {
  const base = getApiBase();
  if (!base) {
    throw new Error(
      "VITE_API_URL is not set. Add it to frontend/.env (e.g. VITE_API_URL=http://localhost:8000)"
    );
  }
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      for (const item of v) {
        if (item !== undefined && item !== null && item !== "") {
          qs.append(k, String(item));
        }
      }
    } else {
      qs.set(k, String(v));
    }
  }
  const q = qs.toString();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}${q ? `?${q}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * @param {string} path e.g. "/api/query"
 * @param {unknown} body JSON-serializable
 */
export async function apiPost(path, body) {
  const base = getApiBase();
  if (!base) {
    throw new Error(
      "VITE_API_URL is not set. Add it to frontend/.env (e.g. VITE_API_URL=http://localhost:8000)"
    );
  }
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}
