/**
 * Projected retirement (EIA planned or commission + life) can fall before the current year
 * while the plant still appears in operating inventory — show a short label; details in tooltip.
 */

/**
 * @param {number | null | undefined} year
 * @returns {boolean}
 */
export function isRetirementYearInPast(year) {
  if (year == null || typeof year !== "number") return false;
  const y = Math.floor(year);
  return y < new Date().getFullYear();
}

/** Replaces the raw year in dense views (table, cards). Tooltip carries the full explanation. */
export const PAST_RETIREMENT_LABEL = "Projection in Past";

/** Tooltip when the cell shows {@link PAST_RETIREMENT_LABEL} instead of the year. */
export function pastRetirementTooltip(year) {
  if (year == null) return "";
  return `Projected retirement ${year}. By that projection the plant should already be closed; it still appears in EIA operating data, so the timeline is not current.`;
}
