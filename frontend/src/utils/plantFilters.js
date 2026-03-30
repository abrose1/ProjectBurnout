/** Default table filters (browse mode). */
export const DEFAULT_PLANT_FILTERS = {
  fuelType: "all",
  fuelTypes: null,
  sortBy: "stranded_gap",
  sortOrder: "desc",
  emmRegion: null,
  states: null,
  minStrandedGap: null,
  maxStrandedGap: null,
  plantNameContains: null,
  operatorContains: null,
  countyContains: null,
  balancingAuthContains: null,
  statusContains: null,
  commissionYearMin: null,
  commissionYearMax: null,
  plannedRetirementYearMin: null,
  plannedRetirementYearMax: null,
  projectedRetirementYearMin: null,
  projectedRetirementYearMax: null,
  projectedStrandedYearMin: null,
  projectedStrandedYearMax: null,
  nameplateMwMin: null,
  nameplateMwMax: null,
  minCapacityFactor: null,
  maxCapacityFactor: null,
  currentCostPerMwhMin: null,
  currentCostPerMwhMax: null,
  currentRevenuePerMwhMin: null,
  currentRevenuePerMwhMax: null,
  currentProfitMarginMin: null,
  currentProfitMarginMax: null,
};

/**
 * Map GET /api/plants / POST /api/query `filters_applied` to UI state.
 * @param {object} fa
 * @returns {typeof DEFAULT_PLANT_FILTERS}
 */
export function apiFiltersToState(fa) {
  if (!fa || typeof fa !== "object") return { ...DEFAULT_PLANT_FILTERS };
  let states = null;
  if (Array.isArray(fa.states) && fa.states.length > 0) {
    states = fa.states.map((s) => String(s).toUpperCase().slice(0, 2));
  } else if (fa.state != null && String(fa.state).trim() !== "") {
    states = [String(fa.state).toUpperCase().slice(0, 2)];
  }
  let fuelTypes = null;
  if (Array.isArray(fa.fuel_types) && fa.fuel_types.length > 0) {
    fuelTypes = fa.fuel_types.map((f) => String(f).toLowerCase());
  }
  return {
    fuelType: fa.fuel_type ?? "all",
    fuelTypes,
    sortBy: fa.sort_by ?? "stranded_gap",
    sortOrder: fa.sort_order ?? "desc",
    emmRegion: fa.emm_region ?? null,
    states,
    minStrandedGap:
      fa.min_stranded_gap != null ? Number(fa.min_stranded_gap) : null,
    maxStrandedGap:
      fa.max_stranded_gap != null ? Number(fa.max_stranded_gap) : null,
    plantNameContains: fa.plant_name_contains ?? null,
    operatorContains: fa.operator_contains ?? null,
    countyContains: fa.county_contains ?? null,
    balancingAuthContains: fa.balancing_auth_contains ?? null,
    statusContains: fa.status_contains ?? null,
    commissionYearMin:
      fa.commission_year_min != null ? Number(fa.commission_year_min) : null,
    commissionYearMax:
      fa.commission_year_max != null ? Number(fa.commission_year_max) : null,
    plannedRetirementYearMin:
      fa.planned_retirement_year_min != null
        ? Number(fa.planned_retirement_year_min)
        : null,
    plannedRetirementYearMax:
      fa.planned_retirement_year_max != null
        ? Number(fa.planned_retirement_year_max)
        : null,
    projectedRetirementYearMin:
      fa.projected_retirement_year_min != null
        ? Number(fa.projected_retirement_year_min)
        : null,
    projectedRetirementYearMax:
      fa.projected_retirement_year_max != null
        ? Number(fa.projected_retirement_year_max)
        : null,
    projectedStrandedYearMin:
      fa.projected_stranded_year_min != null
        ? Number(fa.projected_stranded_year_min)
        : null,
    projectedStrandedYearMax:
      fa.projected_stranded_year_max != null
        ? Number(fa.projected_stranded_year_max)
        : null,
    nameplateMwMin:
      fa.nameplate_mw_min != null ? Number(fa.nameplate_mw_min) : null,
    nameplateMwMax:
      fa.nameplate_mw_max != null ? Number(fa.nameplate_mw_max) : null,
    minCapacityFactor:
      fa.min_capacity_factor != null ? Number(fa.min_capacity_factor) : null,
    maxCapacityFactor:
      fa.max_capacity_factor != null ? Number(fa.max_capacity_factor) : null,
    currentCostPerMwhMin:
      fa.current_cost_per_mwh_min != null
        ? Number(fa.current_cost_per_mwh_min)
        : null,
    currentCostPerMwhMax:
      fa.current_cost_per_mwh_max != null
        ? Number(fa.current_cost_per_mwh_max)
        : null,
    currentRevenuePerMwhMin:
      fa.current_revenue_per_mwh_min != null
        ? Number(fa.current_revenue_per_mwh_min)
        : null,
    currentRevenuePerMwhMax:
      fa.current_revenue_per_mwh_max != null
        ? Number(fa.current_revenue_per_mwh_max)
        : null,
    currentProfitMarginMin:
      fa.current_profit_margin_min != null
        ? Number(fa.current_profit_margin_min)
        : null,
    currentProfitMarginMax:
      fa.current_profit_margin_max != null
        ? Number(fa.current_profit_margin_max)
        : null,
  };
}

/**
 * Build GET /api/plants query params from UI filter state (omit unset values).
 * @param {typeof DEFAULT_PLANT_FILTERS} f
 * @param {{ limit: number; offset: number }} page
 */
export function buildPlantQueryParams(f, page) {
  const p = {
    fuel_type: f.fuelType,
    sort_by: f.sortBy,
    sort_order: f.sortOrder,
    limit: page.limit,
    offset: page.offset,
  };
  if (f.emmRegion) p.emm_region = f.emmRegion;
  if (f.fuelTypes?.length) {
    p.fuel_types = f.fuelTypes;
    p.fuel_type = "all";
  }
  if (f.states?.length) p.states = f.states;
  if (f.minStrandedGap != null) p.min_stranded_gap = f.minStrandedGap;
  if (f.maxStrandedGap != null) p.max_stranded_gap = f.maxStrandedGap;
  if (f.plantNameContains) p.plant_name_contains = f.plantNameContains;
  if (f.operatorContains) p.operator_contains = f.operatorContains;
  if (f.countyContains) p.county_contains = f.countyContains;
  if (f.balancingAuthContains)
    p.balancing_auth_contains = f.balancingAuthContains;
  if (f.statusContains) p.status_contains = f.statusContains;
  if (f.commissionYearMin != null)
    p.commission_year_min = f.commissionYearMin;
  if (f.commissionYearMax != null)
    p.commission_year_max = f.commissionYearMax;
  if (f.plannedRetirementYearMin != null)
    p.planned_retirement_year_min = f.plannedRetirementYearMin;
  if (f.plannedRetirementYearMax != null)
    p.planned_retirement_year_max = f.plannedRetirementYearMax;
  if (f.projectedRetirementYearMin != null)
    p.projected_retirement_year_min = f.projectedRetirementYearMin;
  if (f.projectedRetirementYearMax != null)
    p.projected_retirement_year_max = f.projectedRetirementYearMax;
  if (f.projectedStrandedYearMin != null)
    p.projected_stranded_year_min = f.projectedStrandedYearMin;
  if (f.projectedStrandedYearMax != null)
    p.projected_stranded_year_max = f.projectedStrandedYearMax;
  if (f.nameplateMwMin != null) p.nameplate_mw_min = f.nameplateMwMin;
  if (f.nameplateMwMax != null) p.nameplate_mw_max = f.nameplateMwMax;
  if (f.minCapacityFactor != null)
    p.min_capacity_factor = f.minCapacityFactor;
  if (f.maxCapacityFactor != null)
    p.max_capacity_factor = f.maxCapacityFactor;
  if (f.currentCostPerMwhMin != null)
    p.current_cost_per_mwh_min = f.currentCostPerMwhMin;
  if (f.currentCostPerMwhMax != null)
    p.current_cost_per_mwh_max = f.currentCostPerMwhMax;
  if (f.currentRevenuePerMwhMin != null)
    p.current_revenue_per_mwh_min = f.currentRevenuePerMwhMin;
  if (f.currentRevenuePerMwhMax != null)
    p.current_revenue_per_mwh_max = f.currentRevenuePerMwhMax;
  if (f.currentProfitMarginMin != null)
    p.current_profit_margin_min = f.currentProfitMarginMin;
  if (f.currentProfitMarginMax != null)
    p.current_profit_margin_max = f.currentProfitMarginMax;
  return p;
}

const CORE_KEYS = new Set([
  "fuelType",
  "fuelTypes",
  "sortBy",
  "sortOrder",
  "emmRegion",
  "states",
  "minStrandedGap",
]);

/**
 * Count of “advanced” (non-toolbar) filters for compact NL chip UI.
 * @param {typeof DEFAULT_PLANT_FILTERS} f
 */
/**
 * @param {typeof DEFAULT_PLANT_FILTERS} f
 */
export function isFiltersDefault(f) {
  for (const k of Object.keys(DEFAULT_PLANT_FILTERS)) {
    const a = f[k];
    const b = DEFAULT_PLANT_FILTERS[k];
    if (Array.isArray(a) || Array.isArray(b)) {
      const aa = a ?? [];
      const bb = b ?? [];
      if (aa.length !== bb.length) return false;
      if (aa.some((x, i) => x !== bb[i])) return false;
    } else if (a !== b) {
      return false;
    }
  }
  return true;
}

export function countAdvancedFilters(f) {
  let n = 0;
  for (const k of Object.keys(DEFAULT_PLANT_FILTERS)) {
    if (CORE_KEYS.has(k)) continue;
    const dv = DEFAULT_PLANT_FILTERS[k];
    const v = f[k];
    if (v !== dv && v != null) n++;
  }
  return n;
}

/**
 * Clear NL-only / numeric / text filters; keep fuel, region, states, sort, gap min.
 * @param {typeof DEFAULT_PLANT_FILTERS} f
 */
export function resetAdvancedFilters(f) {
  const next = { ...f };
  for (const k of Object.keys(DEFAULT_PLANT_FILTERS)) {
    if (CORE_KEYS.has(k)) continue;
    next[k] = DEFAULT_PLANT_FILTERS[k];
  }
  return next;
}
