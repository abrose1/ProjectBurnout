import { useCallback, useState } from "react";
import { apiPost, getApiBase } from "../utils/api";

/**
 * POST /api/query — natural language → structured filters + message.
 * @returns {{
 *   submit: (query: string) => Promise<{ message: string; filters_applied: object | null; fallback: boolean } | void>;
 *   loading: boolean;
 *   error: string | null;
 *   clearError: () => void;
 * }}
 */
export function useNlQuery() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const submit = useCallback(async (query) => {
    const q = String(query ?? "").trim();
    if (!q) {
      setError("Enter a search or question.");
      return undefined;
    }
    if (!getApiBase()) {
      setError("Configure VITE_API_URL to use search.");
      return undefined;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost("/api/query", { query: q });
      return {
        message: data.message ?? "",
        filters_applied: data.filters_applied ?? null,
        fallback: Boolean(data.fallback),
      };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { submit, loading, error, clearError };
}
