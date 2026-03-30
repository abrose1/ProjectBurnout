import { useEffect, useId, useRef } from "react";
import { usePlantDetail } from "../hooks/usePlantDetail";
import { MetricSparkline } from "./MetricSparkline";
import {
  isRetirementYearInPast,
  pastRetirementTooltip,
} from "../utils/retirementDisplay";

function formatYear(y) {
  if (y == null) return null;
  return String(y);
}

function formatCountyState(county, state) {
  const c = county?.trim();
  if (c) return `${c}, ${state}`;
  return state;
}

/**
 * Prefer a filed/planned year when present; otherwise show model projection.
 * @returns {{ kind: 'filing' | 'model' | 'empty'; year: string | null; kicker: string; note: string; past: boolean; pastSummary: string | null; yearDetailLabel: string | null }}
 */
function retirementLine(data) {
  const planned = data.planned_retirement_year;
  const projected = data.projected_retirement_year;

  if (planned != null) {
    const past = isRetirementYearInPast(planned);
    return {
      kind: "filing",
      year: formatYear(planned),
      kicker: "Reported in filings",
      note: past
        ? "Planned retirement comes from EIA; when that projection is in the past, the unit was often extended or filings have not caught up."
        : "Planned retirement year from EIA operating generator capacity records.",
      past,
      pastSummary: past
        ? "By our projected retirement date, this plant should already be closed; it is still operating, so that projection is not a current shutdown schedule."
        : null,
      yearDetailLabel: past ? "Projection year" : null,
    };
  }
  if (projected != null) {
    const past = isRetirementYearInPast(projected);
    return {
      kind: "model",
      year: formatYear(projected),
      kicker: "Projected (our model)",
      note: past
        ? "Without an EIA filing we use commission year plus typical plant life; when that projection is in the past, the unit may simply be running longer than the estimate."
        : "Projected retirement year when no EIA filing: commission year plus typical coal or gas life.",
      past,
      pastSummary: past
        ? "By our projected retirement date, this plant should already be past its modeled shutdown horizon; it is still operating, so treat the year as a rough estimate."
        : null,
      yearDetailLabel: past ? "Projection year" : null,
    };
  }
  return {
    kind: "empty",
    year: null,
    kicker: "No year on file",
    note: "We do not have a filed planned retirement or a model projection for this plant yet.",
    past: false,
    pastSummary: null,
    yearDetailLabel: null,
  };
}

function RetirementSection({ data }) {
  const r = retirementLine(data);
  const tooltip =
    r.past && r.year != null ? pastRetirementTooltip(Number(r.year)) : undefined;
  return (
    <section
      className="plant-detail-modal__section plant-detail-modal__retire"
      aria-label="Retirement"
    >
      <h3 className="plant-detail-modal__section-label">Retirement</h3>
      <div
        className={`plant-detail-modal__retire-block plant-detail-modal__retire-block--${r.kind}${
          r.past ? " plant-detail-modal__retire-block--past" : ""
        }`}
      >
        <span
          className={`plant-detail-modal__retire-kicker ${
            r.kind === "model" ? "plant-detail-modal__retire-kicker--projected" : ""
          }`}
        >
          {r.kicker}
        </span>
        {r.past && r.pastSummary != null ? (
          <>
            <p className="plant-detail-modal__retire-past-summary">{r.pastSummary}</p>
            <p
              className="plant-detail-modal__retire-year-secondary num"
              title={tooltip}
            >
              <span className="muted">{r.yearDetailLabel}: </span>
              {r.year ?? "—"}
            </p>
          </>
        ) : (
          <span className="plant-detail-modal__retire-year num">{r.year ?? "—"}</span>
        )}
        <span className="plant-detail-modal__retire-note muted">{r.note}</span>
      </div>
    </section>
  );
}

/**
 * @param {{ plantId: string | null; open: boolean; onClose: () => void }} props
 */
export function PlantDetailModal({ plantId, open, onClose }) {
  const titleId = useId();
  const closeRef = useRef(null);
  const { data, loading, error } = usePlantDetail(open ? plantId : null);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => closeRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open, plantId]);

  useEffect(() => {
    if (!open) return;
    function onKey(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const fuelClass =
    data?.primary_fuel === "coal" ? "coal" : "gas";

  return (
    <div className="plant-detail-modal" role="presentation">
      <button
        type="button"
        className="plant-detail-modal__backdrop"
        aria-label="Close plant details"
        tabIndex={-1}
        onClick={onClose}
      />
      <div
        className="plant-detail-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="plant-detail-modal__topbar">
          <button
            ref={closeRef}
            type="button"
            className="plant-detail-modal__close btn btn--secondary"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        {loading && !data && (
          <div className="plant-detail-modal__body plant-detail-modal__body--loading">
            <div className="skeleton skeleton--label plant-detail-modal__sk-title" />
            <div className="skeleton skeleton--value plant-detail-modal__sk-line" />
            <div className="skeleton skeleton--row plant-detail-modal__sk-block" />
          </div>
        )}

        {error && !loading && (
          <div className="plant-detail-modal__body">
            <p className="banner banner--error plant-detail-modal__err">
              {error}
            </p>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={onClose}
            >
              Dismiss
            </button>
          </div>
        )}

        {data && (
          <div className="plant-detail-modal__body">
            <header className="plant-detail-modal__hero">
              <p className="plant-detail-modal__eyebrow">Plant</p>
              <h2 id={titleId} className="plant-detail-modal__title">
                {data.plant_name}
              </h2>
              <p className="plant-detail-modal__lede">
                <span
                  className={`fuel-dot fuel-dot--${fuelClass}`}
                  aria-hidden
                />
                {data.primary_fuel} ·{" "}
                <span className="num">
                  {data.nameplate_mw.toLocaleString(undefined, {
                    maximumFractionDigits: 1,
                  })}
                </span>{" "}
                MW
                <span className="plant-detail-modal__id muted">
                  {" "}
                  · {data.plant_id}
                </span>
              </p>
            </header>

            <section
              className="plant-detail-modal__section"
              aria-label="Location"
            >
              <p className="plant-detail-modal__place">
                {formatCountyState(data.county, data.state)}
              </p>
              {data.emm_region && (
                <p className="plant-detail-modal__region muted">
                  EMM region {data.emm_region}
                </p>
              )}
            </section>

            <section
              className="plant-detail-modal__section plant-detail-modal__section--split"
              aria-label="Operator and commission"
            >
              <div className="plant-detail-modal__fact">
                <span className="plant-detail-modal__fact-label">
                  Operator
                </span>
                <span className="plant-detail-modal__fact-value">
                  {data.operator_name?.trim() || "—"}
                </span>
              </div>
              <div className="plant-detail-modal__fact">
                <span className="plant-detail-modal__fact-label">
                  Commissioned
                </span>
                <span className="plant-detail-modal__fact-value num">
                  {formatYear(data.commission_year) ?? "—"}
                </span>
              </div>
            </section>

            <RetirementSection data={data} />

            <section
              className="plant-detail-modal__section plant-detail-modal__section--chart"
              aria-label="Capacity factor over time"
            >
              <h3 className="plant-detail-modal__section-label">
                Capacity factor
              </h3>
              <p className="plant-detail-modal__section-hint muted">
                Annual average — higher means the unit ran closer to its
                nameplate capacity.
              </p>
              <MetricSparkline metrics={data.metrics} />
            </section>

            {data.metrics && data.metrics.length > 0 && (
              <details className="plant-detail-modal__raw">
                <summary className="plant-detail-modal__raw-summary">
                  Year-by-year numbers
                </summary>
                <div className="plant-detail-modal__raw-scroll">
                  <table className="plant-detail-modal__raw-table">
                    <thead>
                      <tr>
                        <th scope="col">Year</th>
                        <th scope="col">Capacity Factor</th>
                        <th scope="col">Gen (MWh)</th>
                        <th scope="col">$/MWh</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...data.metrics]
                        .sort((a, b) => b.year - a.year)
                        .map((m) => (
                          <tr key={m.year}>
                            <td className="num">{m.year}</td>
                            <td className="num">
                              {m.capacity_factor != null
                                ? `${(m.capacity_factor * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`
                                : "—"}
                            </td>
                            <td className="num">
                              {m.net_generation_mwh != null
                                ? m.net_generation_mwh.toLocaleString(undefined, {
                                    maximumFractionDigits: 0,
                                  })
                                : "—"}
                            </td>
                            <td className="num">
                              {m.fuel_cost_per_mwh != null
                                ? m.fuel_cost_per_mwh.toLocaleString(undefined, {
                                    maximumFractionDigits: 1,
                                  })
                                : "—"}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
