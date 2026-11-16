import { getOrCreateVisitorId } from "./visitorId.js";

/** @returns {Record<string, string>} */
function visitorHeaders() {
  const vid = getOrCreateVisitorId();
  if (!vid) return {};
  return { "X-Visitor-Id": vid };
}

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
  const res = await fetch(url, { headers: { ...visitorHeaders() } });
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
    headers: {
      "Content-Type": "application/json",
      ...visitorHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

const APP_LOAD_SESSION_KEY = "burnout_app_load_logged";

/** Record one app_load event per browser tab session (best-effort). */
export async function recordAppLoadVisit() {
  try {
    if (!getApiBase()) return;
    if (typeof sessionStorage !== "undefined" && sessionStorage.getItem(APP_LOAD_SESSION_KEY) === "1") {
      return;
    }
    await apiPost("/api/analytics/visit", { event_type: "app_load" });
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.setItem(APP_LOAD_SESSION_KEY, "1");
    }
  } catch {
    /* ignore analytics failures */
  }
}
