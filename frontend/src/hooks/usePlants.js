import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, getApiBase } from "../utils/api";
import { buildPlantQueryParams } from "../utils/plantFilters";

const PAGE_SIZE_DESKTOP = 50;
const PAGE_SIZE_MOBILE = 10;

const MOBILE_MAX_WIDTH = "(max-width: 639px)";

function usePlantsPageSize() {
  const [pageSize, setPageSize] = useState(() => {
    if (typeof window === "undefined") return PAGE_SIZE_DESKTOP;
    return window.matchMedia(MOBILE_MAX_WIDTH).matches
      ? PAGE_SIZE_MOBILE
      : PAGE_SIZE_DESKTOP;
  });

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MAX_WIDTH);
    const sync = () =>
      setPageSize(mq.matches ? PAGE_SIZE_MOBILE : PAGE_SIZE_DESKTOP);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  return pageSize;
}

/** @param {Record<string, unknown>} filters — UI plant filter state from `plantFilters.js` */
export function usePlants(filters) {
  const pageSize = usePlantsPageSize();
  const [plants, setPlants] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  const requestIdRef = useRef(0);

  const fetchPage = useCallback(
    async (offset, append) => {
      const id = ++requestIdRef.current;
      if (!getApiBase()) {
        setPlants([]);
        setTotal(0);
        setError(null);
        setLoading(false);
        setLoadingMore(false);
        return;
      }
      const isFirst = !append;
      if (isFirst) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }
      setError(null);
      try {
        const params = buildPlantQueryParams(filters, {
          limit: pageSize,
          offset,
        });
        const data = await apiGet("/api/plants", params);
        if (id !== requestIdRef.current) return;
        setTotal(data.total);
        setPlants((prev) => (append ? [...prev, ...data.items] : data.items));
      } catch (e) {
        if (id !== requestIdRef.current) return;
        setError(e instanceof Error ? e.message : String(e));
        if (!append) setPlants([]);
      } finally {
        if (id === requestIdRef.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [filters, pageSize]
  );

  useEffect(() => {
    fetchPage(0, false);
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (loading || loadingMore) return;
    if (plants.length >= total) return;
    fetchPage(plants.length, true);
  }, [fetchPage, loading, loadingMore, plants.length, total]);

  const refetch = useCallback(() => {
    fetchPage(0, false);
  }, [fetchPage]);

  const hasMore = plants.length < total;

  return {
    plants,
    total,
    loading,
    loadingMore,
    error,
    loadMore,
    refetch,
    hasMore,
    pageSize,
  };
}
