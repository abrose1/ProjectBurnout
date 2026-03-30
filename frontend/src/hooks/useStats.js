import { useCallback, useEffect, useState } from "react";
import { apiGet, getApiBase } from "../utils/api";

export function useStats() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retryKey, setRetryKey] = useState(0);

  const refetch = useCallback(() => setRetryKey((k) => k + 1), []);

  useEffect(() => {
    if (!getApiBase()) {
      setStats(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiGet("/api/stats");
        if (!cancelled) setStats(data);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setStats(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [retryKey]);

  return { stats, loading, error, refetch };
}
