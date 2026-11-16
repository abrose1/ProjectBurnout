const STORAGE_KEY = "burnout_visitor_id";

/**
 * Stable anonymous id per browser profile (localStorage). Used as X-Visitor-Id on API calls.
 * @returns {string | null}
 */
export function getOrCreateVisitorId() {
  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (
      existing &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(existing)
    ) {
      return existing.toLowerCase();
    }
    const id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, id);
    return id;
  } catch {
    return null;
  }
}
