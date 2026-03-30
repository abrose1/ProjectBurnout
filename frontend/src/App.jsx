import { useCallback, useState } from "react";
import { CursorFx } from "./components/CursorFx";
import { Layout } from "./components/Layout";
import { PlantTable } from "./components/PlantTable";
import { QueryBar } from "./components/QueryBar";
import { useStats } from "./hooks/useStats";
import { DEFAULT_PLANT_FILTERS } from "./utils/plantFilters";

function App() {
  const { stats, loading: statsLoading, error: statsError, refetch: refetchStats } =
    useStats();
  const [filters, setFilters] = useState(() => ({ ...DEFAULT_PLANT_FILTERS }));
  const [nlBanner, setNlBanner] = useState(null);

  const onNlMessage = useCallback((msg, opts) => {
    if (msg == null) {
      setNlBanner(null);
      return;
    }
    setNlBanner({
      message: msg,
      variant: opts?.variant ?? "success",
      fallback: Boolean(opts?.fallback),
    });
  }, []);

  return (
    <>
      <Layout>
        <div className="content-stack">
          <QueryBar
            onFiltersChange={setFilters}
            onNlMessage={onNlMessage}
            interpretation={nlBanner}
          />
          <PlantTable
            filters={filters}
            onFiltersChange={setFilters}
            onManualFilterAdjust={() => setNlBanner(null)}
            totalPlantsInDb={stats?.total_plants}
            statsLoading={statsLoading}
            statsError={statsError}
            onStatsRetry={refetchStats}
          />
        </div>
      </Layout>
      <CursorFx />
    </>
  );
}

export default App;
