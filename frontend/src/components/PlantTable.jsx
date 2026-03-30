import { useState } from "react";
import { usePlants } from "../hooks/usePlants";
import { useRegions } from "../hooks/useRegions";
import { getApiBase } from "../utils/api";
import {
  isRetirementYearInPast,
  PAST_RETIREMENT_LABEL,
  pastRetirementTooltip,
} from "../utils/retirementDisplay";
import { ErrorBanner } from "./ErrorBanner";
import { PlantDetailModal } from "./PlantDetailModal";

const SORTS = [
  { key: "stranded_gap", label: "Stranded Gap (yrs)" },
  { key: "projected_stranded_year", label: "Stranded Year" },
  {
    key: "projected_retirement_year",
    label: "Projected Retirement",
    thTitle:
      "EIA planned retirement where available, else commission year + typical life. If that projection is already in the past, we show a short label instead of the year (hover for detail).",
  },
  { key: "capacity_factor", label: "Latest Capacity Factor" },
  { key: "nameplate_mw", label: "MW" },
  { key: "cost_per_mwh", label: "$/MWh" },
];

const SKELETON_ROWS = 8;

/** Shown when retirement is modeled before the first economically stranded year (negative gap). */
const GAP_NEGATIVE_LABEL = "Retires before stranding";

function formatGapYears(gap) {
  if (gap == null) return "—";
  return gap.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

/** Table / summary: number of years, short phrase for negative gap, em dash if unknown. */
function formatGap(gap) {
  if (gap == null) return "—";
  if (gap < 0) return GAP_NEGATIVE_LABEL;
  return formatGapYears(gap);
}

function formatYear(y) {
  if (y == null) return "—";
  return String(y);
}

function formatMw(mw) {
  return mw.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function formatCf(cf) {
  if (cf == null) return "—";
  return `${(cf * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

/**
 * Larger stranded gap (years) ⇒ worse exposure. Used only for gap cell text color.
 * Negative gaps are low concern (muted); zero is mild.
 */
function gapValueTone(gap) {
  if (gap == null) return "none";
  if (gap < 0) return "none";
  if (gap <= 5) return "mild";
  if (gap <= 10) return "moderate";
  if (gap <= 15) return "serious";
  return "severe";
}

/** When gap is null: no stranded year in horizon vs missing retirement year. */
const GAP_NULL_NO_STRANDED_LABEL = "Not projected to become stranded";
const GAP_NULL_NO_RETIREMENT_LABEL = "Retirement year missing";

/**
 * @returns {{ label: string; gapTone: string; gapStrong: boolean }}
 */
function gapDisplayInfo(gap, projectedStrandedYear, projectedRetirementYear) {
  if (gap != null) {
    return {
      label: formatGap(gap),
      gapTone: gapValueTone(gap),
      gapStrong: gap >= 0,
    };
  }
  if (projectedStrandedYear == null) {
    return {
      label: GAP_NULL_NO_STRANDED_LABEL,
      gapTone: "none",
      gapStrong: false,
    };
  }
  if (projectedRetirementYear == null) {
    return {
      label: GAP_NULL_NO_RETIREMENT_LABEL,
      gapTone: "none",
      gapStrong: false,
    };
  }
  return {
    label: "—",
    gapTone: "none",
    gapStrong: false,
  };
}

const TABLE_COL_COUNT = 10;

function TableSkeletonRows() {
  return (
    <>
      {Array.from({ length: SKELETON_ROWS }, (_, i) => (
        <tr key={i} className="plant-table__skeleton-row" aria-hidden>
          <td colSpan={TABLE_COL_COUNT}>
            <div className="skeleton skeleton--row" />
          </td>
        </tr>
      ))}
    </>
  );
}

/**
 * @param {{
 *   filters: object;
 *   onFiltersChange: (f: object) => void;
 *   onManualFilterAdjust?: () => void;
 *   totalPlantsInDb?: number;
 *   statsLoading?: boolean;
 *   statsError?: string | null;
 *   onStatsRetry?: () => void;
 * }} props
 * totalPlantsInDb from GET /api/stats — distinguishes empty DB vs empty filter.
 */
function formatTrackedCount(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString();
}

export function PlantTable({
  filters,
  onFiltersChange,
  onManualFilterAdjust,
  totalPlantsInDb,
  statsLoading = false,
  statsError = null,
  onStatsRetry,
}) {
  const {
    fuelType,
    sortBy,
    sortOrder,
    emmRegion,
    states,
    fuelTypes,
    minStrandedGap,
    maxStrandedGap,
  } = filters;
  const [detailPlantId, setDetailPlantId] = useState(null);

  const { items: regionItems, loading: regionsLoading } = useRegions();
  const {
    plants,
    total,
    loading,
    loadingMore,
    error,
    loadMore,
    refetch,
    hasMore,
  } = usePlants(filters);

  function setPartial(partial) {
    onManualFilterAdjust?.();
    onFiltersChange({ ...filters, ...partial });
  }

  const missingBase = getApiBase() === "";

  function openPlantDetail(plantId) {
    setDetailPlantId(plantId);
  }

  function closePlantDetail() {
    setDetailPlantId(null);
  }

  /**
   * @param {React.KeyboardEvent | React.MouseEvent} e
   * @param {string} plantId
   */
  function onPlantActivate(e, plantId) {
    if (e.type === "keydown") {
      const ke = /** @type {React.KeyboardEvent} */ (e);
      if (ke.key !== "Enter" && ke.key !== " ") return;
      ke.preventDefault();
    }
    openPlantDetail(plantId);
  }

  function onSortClick(key) {
    if (key === sortBy) {
      setPartial({ sortOrder: sortOrder === "desc" ? "asc" : "desc" });
    } else {
      setPartial({ sortBy: key, sortOrder: "desc" });
    }
  }

  function sortIndicator(key) {
    if (key !== sortBy) return "";
    return sortOrder === "desc" ? " ↓" : " ↑";
  }

  const initialLoading = loading && plants.length === 0;
  const showEmpty =
    !initialLoading && !error && plants.length === 0;
  const emptyAwaitingStats = showEmpty && statsLoading;
  const emptyDb =
    showEmpty && !statsLoading && totalPlantsInDb === 0;
  const emptyFilters =
    showEmpty && !statsLoading && totalPlantsInDb !== undefined && totalPlantsInDb > 0;

  const listTotalNum =
    total != null && !Number.isNaN(Number(total)) ? Number(total) : null;
  const globalTrackedNum =
    totalPlantsInDb != null && !Number.isNaN(Number(totalPlantsInDb))
      ? Number(totalPlantsInDb)
      : null;
  /** Only when global inventory differs from the list total already shown in "of N". */
  const showGlobalTrackedSuffix =
    !statsLoading &&
    !statsError &&
    listTotalNum != null &&
    globalTrackedNum != null &&
    globalTrackedNum !== listTotalNum;

  if (missingBase) {
    return (
      <section aria-label="Power Plants">
        <p className="muted empty-state">
          Configure <code className="inline-code">VITE_API_URL</code> to load the
          plant list.
        </p>
      </section>
    );
  }

  return (
    <section className="plants-block" aria-label="Power Plants">
      <header className="plants-section-head">
        <h3 className="plants-section-head__title">Plants</h3>
      </header>
      <div className="plant-toolbar">
        <div className="plant-toolbar__primary">
          <div
            className="segmented"
            role="group"
            aria-label="Filter by Fuel"
          >
            {(["all", "coal", "gas"]).map((f) => (
              <button
                key={f}
                type="button"
                aria-pressed={!fuelTypes?.length && fuelType === f}
                onClick={() => setPartial({ fuelType: f, fuelTypes: null })}
                disabled={initialLoading && !error}
              >
                {f === "all" ? "All" : f === "coal" ? "Coal" : "Gas"}
              </button>
            ))}
          </div>
          <label className="muted toolbar-label toolbar-label--region">
            <span className="toolbar-label__region-word">Region</span>
            <select
              className="region-select"
              value={emmRegion ?? ""}
              onChange={(e) =>
                setPartial({
                  emmRegion: e.target.value === "" ? null : e.target.value,
                })
              }
              disabled={regionsLoading || (initialLoading && !error)}
              aria-busy={regionsLoading}
            >
              <option value="">
                {regionsLoading ? "Loading Regions…" : "All Regions"}
              </option>
              {regionItems.map((r) => (
                <option key={r.emm_region} value={r.emm_region}>
                  {r.emm_region} ({r.plant_count})
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="plant-toolbar__nl-meta" aria-label="Active search filters">
          {fuelTypes?.length > 0 && (
            <span
              className="muted toolbar-label"
              title="From natural language search"
            >
              Fuels <strong>{fuelTypes.join(", ")}</strong>
            </span>
          )}
          {(states?.length ?? 0) > 0 && (
            <span
              className="muted toolbar-label plant-toolbar__state"
              title="From search or filters"
            >
              State{states.length > 1 ? "s" : ""}{" "}
              <strong>{states.join(", ")}</strong>
            </span>
          )}
          {minStrandedGap != null && (
            <span className="muted toolbar-label" title="Minimum stranded gap in years">
              Gap ≥ <strong>{minStrandedGap}</strong> yrs
            </span>
          )}
          {maxStrandedGap != null && (
            <span className="muted toolbar-label" title="Maximum stranded gap in years">
              Gap ≤ <strong>{maxStrandedGap}</strong> yrs
            </span>
          )}
        </div>
      </div>

      {error && (
        <ErrorBanner
          title="Could Not Load Plants"
          message={error}
          onRetry={refetch}
        />
      )}

      <div
        className="table-wrap"
        aria-busy={initialLoading}
      >
        <table className="plant-table">
          <thead>
            <tr>
              <th
                scope="col"
                className="col-rank"
                title="Position in This List (Filters and Sort Applied)"
              >
                #
              </th>
              <th scope="col">Plant</th>
              <th scope="col">State</th>
              <th scope="col">Fuel</th>
              {SORTS.map(({ key, label, thTitle }) => (
                <th key={key} scope="col" title={thTitle}>
                  <button
                    type="button"
                    onClick={() => onSortClick(key)}
                    disabled={initialLoading && !error}
                  >
                    {label}
                    {sortIndicator(key)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {initialLoading ? (
              <TableSkeletonRows />
            ) : emptyAwaitingStats ? (
              <tr>
                <td colSpan={TABLE_COL_COUNT} className="plant-table__empty">
                  <span className="muted">Loading Summary…</span>
                </td>
              </tr>
            ) : showEmpty ? (
              <tr>
                <td colSpan={TABLE_COL_COUNT} className="plant-table__empty">
                  {emptyDb && (
                    <div className="empty-state">
                      <p className="empty-state__title">No Plant Data Yet</p>
                      <p className="empty-state__body">
                        Run the EIA refresh pipeline from the repo root so the
                        database is populated (see README: Data refresh).
                      </p>
                    </div>
                  )}
                  {emptyFilters && (
                    <div className="empty-state">
                      <p className="empty-state__title">
                        No Plants Match These Filters
                      </p>
                      <p className="empty-state__body">
                        Try a different fuel or region, or clear filters to see
                        the full list.
                      </p>
                    </div>
                  )}
                  {!emptyDb && !emptyFilters && (
                    <div className="empty-state">
                      <p className="empty-state__title">No Results</p>
                      <p className="empty-state__body">
                        Adjust filters or try again in a moment.
                      </p>
                    </div>
                  )}
                </td>
              </tr>
            ) : (
              plants.map((p, index) => {
                const rank = index + 1;
                const gap = p.projection?.stranded_gap_years ?? null;
                const sy = p.projection?.projected_stranded_year ?? null;
                const retire = p.projected_retirement_year ?? null;
                const gInfo = gapDisplayInfo(gap, sy, retire);
                const retirePast = isRetirementYearInPast(retire);
                return (
                  <tr
                    key={p.plant_id}
                    className="plant-row plant-row--clickable"
                    tabIndex={0}
                    aria-label={`${p.plant_name}, rank ${rank} of ${total}. Press Enter or Space for details.`}
                    onClick={() => openPlantDetail(p.plant_id)}
                    onKeyDown={(e) => onPlantActivate(e, p.plant_id)}
                  >
                    <td className="num col-rank">{rank}</td>
                    <th scope="row" className="col-name">
                      {p.plant_name}
                    </th>
                    <td>{p.state}</td>
                    <td>
                      <span
                        className={`fuel-dot fuel-dot--${p.primary_fuel === "coal" ? "coal" : "gas"}`}
                        aria-hidden
                      />
                      {p.primary_fuel}
                    </td>
                    <td className="num col-num">
                      <span
                        className={`${
                          gInfo.gapStrong ? "gap-strong " : ""
                        }gap-value gap-value--${gInfo.gapTone}`}
                      >
                        {gInfo.label}
                      </span>
                    </td>
                    <td className="num col-num">{formatYear(sy)}</td>
                    <td
                      className={`num col-num${
                        retirePast ? " retirement-cell retirement-cell--past" : ""
                      }`}
                    >
                      {retirePast ? (
                        <span
                          className="retirement-cell__past-label"
                          title={pastRetirementTooltip(retire)}
                        >
                          {PAST_RETIREMENT_LABEL}
                        </span>
                      ) : (
                        formatYear(retire)
                      )}
                    </td>
                    <td className="num col-num">{formatCf(p.latest_capacity_factor)}</td>
                    <td className="num col-num">{formatMw(p.nameplate_mw)}</td>
                    <td className="num col-num">
                      {p.projection?.current_cost_per_mwh != null
                        ? p.projection.current_cost_per_mwh.toLocaleString(
                            undefined,
                            { maximumFractionDigits: 1 }
                          )
                        : "—"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="plant-cards" aria-label="Plant List (Mobile)">
        {initialLoading ? (
          <div className="plant-cards-skeleton" aria-hidden>
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="skeleton skeleton--card" />
            ))}
          </div>
        ) : emptyAwaitingStats ? (
          <p className="muted empty-state">Loading Summary…</p>
        ) : showEmpty ? (
          <div className="empty-state empty-state--mobile">
            {emptyDb && (
              <>
                <p className="empty-state__title">No Plant Data Yet</p>
                <p className="empty-state__body">
                  Run the EIA refresh pipeline (see README).
                </p>
              </>
            )}
            {emptyFilters && (
              <>
                <p className="empty-state__title">No Plants Match</p>
                <p className="empty-state__body">Try other filters.</p>
              </>
            )}
            {!emptyDb && !emptyFilters && (
              <p className="empty-state__body">No Results.</p>
            )}
          </div>
        ) : (
          plants.map((p, index) => {
            const rank = index + 1;
            const gap = p.projection?.stranded_gap_years ?? null;
            const sy = p.projection?.projected_stranded_year ?? null;
            const retire = p.projected_retirement_year ?? null;
            const gInfo = gapDisplayInfo(gap, sy, retire);
            const retirePast = isRetirementYearInPast(retire);
            const gapMobileText =
              gap != null
                ? gap < 0
                  ? `Gap: ${GAP_NEGATIVE_LABEL}`
                  : `Gap: ${formatGapYears(gap)} yrs`
                : `Gap: ${gInfo.label}`;
            return (
              <article
                key={p.plant_id}
                className="plant-card plant-card--clickable"
                tabIndex={0}
                role="button"
                aria-label={`${p.plant_name}, ${p.primary_fuel}, rank ${rank} of ${total}. Activate for details.`}
                onClick={() => openPlantDetail(p.plant_id)}
                onKeyDown={(e) => onPlantActivate(e, p.plant_id)}
              >
                <div className="plant-card__top">
                  <span className="plant-card__rank" aria-hidden>
                    #{rank}
                  </span>
                  <h2 className="plant-card__name">{p.plant_name}</h2>
                  <span className="plant-card__state">{p.state}</span>
                </div>
                <div className="plant-card__meta">
                  <div className="plant-card__summary">
                    <span className="plant-card__mw">
                      {formatMw(p.nameplate_mw)} MW
                    </span>
                    <span className="plant-card__fuel">
                      {p.primary_fuel === "coal" ? "Coal" : "Gas"}
                    </span>
                  </div>
                  <p
                    className={`plant-card__gap-line ${
                      gInfo.gapStrong ? "gap-strong " : ""
                    }gap-value gap-value--${gInfo.gapTone}`}
                  >
                    {gapMobileText}
                  </p>
                  <div className="plant-card__years">
                    <div className="plant-card__year-cell">
                      <span className="plant-card__year-label">
                        Stranded year
                      </span>
                      <span className="num">{formatYear(sy)}</span>
                    </div>
                    <div
                      className={`plant-card__year-cell${
                        retirePast ? " plant-card__year-cell--past" : ""
                      }`}
                    >
                      <span className="plant-card__year-label">
                        Retirement year
                      </span>
                      <span className="num">
                        {retirePast ? (
                          <span
                            className="retirement-cell__past-label"
                            title={pastRetirementTooltip(retire)}
                          >
                            {PAST_RETIREMENT_LABEL}
                          </span>
                        ) : (
                          formatYear(retire)
                        )}
                      </span>
                    </div>
                  </div>
                </div>
              </article>
            );
          })
        )}
      </div>

      <PlantDetailModal
        plantId={detailPlantId}
        open={detailPlantId != null}
        onClose={closePlantDetail}
      />

      <div className="load-more-wrap">
        <p
          className="muted load-more-summary"
          title="List scope from GET /api/plants; global total from GET /api/stats when it differs from the list total"
        >
          {error ? (
            "Could Not Load Plant Counts."
          ) : statsError ? (
            <>
              Showing {plants.length.toLocaleString()} of{" "}
              {total.toLocaleString()} matches — could not load total plants tracked.{" "}
              {onStatsRetry && (
                <button
                  type="button"
                  className="btn btn--secondary btn--inline"
                  onClick={onStatsRetry}
                >
                  Retry
                </button>
              )}
            </>
          ) : showGlobalTrackedSuffix ? (
            <>
              Showing {plants.length.toLocaleString()} of{" "}
              {total.toLocaleString()} matches out of{" "}
              <strong className="load-more-summary__count">
                {formatTrackedCount(totalPlantsInDb)}
              </strong>{" "}
              total plants tracked
            </>
          ) : (
            <>
              Showing {plants.length.toLocaleString()} of{" "}
              {total.toLocaleString()} matches
            </>
          )}
        </p>
        <button
          type="button"
          className="btn btn--primary"
          onClick={loadMore}
          disabled={
            !hasMore || loadingMore || loading || Boolean(error)
          }
        >
          {loadingMore
            ? "Loading More…"
            : error
              ? "Fix Error to Load More"
              : hasMore
                ? "Load More"
                : "End of List"}
        </button>
      </div>
    </section>
  );
}
