import { useEffect, useState } from "react";
import { apiGet, getApiBase } from "../utils/api";

/**
 * @param {string | null} plantId
 */
export function usePlantDetail(plantId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!plantId || getApiBase() === "") {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    const path = `/api/plants/${encodeURIComponent(plantId)}`;
    apiGet(path)
      .then((json) => {
        if (!cancelled) {
          setData(json);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [plantId]);

  return { data, loading, error };
}
