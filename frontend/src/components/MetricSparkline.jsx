import { useId } from "react";

/**
 * Minimal SVG sparkline for capacity factor (0–1) over time.
 * X position follows calendar year so gaps in data do not distort spacing.
 */
export function MetricSparkline({ metrics }) {
  const gradId = useId().replace(/:/g, "");
  const series = (metrics ?? [])
    .filter((m) => m.capacity_factor != null)
    .map((m) => ({ year: m.year, cf: m.capacity_factor }));

  if (series.length === 0) {
    return (
      <p className="plant-detail-modal__spark-empty muted">
        No capacity factor history in this dataset.
      </p>
    );
  }

  const years = series.map((s) => s.year);
  const minY = Math.min(...years);
  const maxY = Math.max(...years);
  const span = Math.max(maxY - minY, 1);

  const pad = 2;
  const innerW = 100 - pad * 2;
  const innerH = 36 - pad * 2;

  const pts = series.map((s) => {
    const x = pad + ((s.year - minY) / span) * innerW;
    const y = pad + (1 - s.cf) * innerH;
    return `${x},${y}`;
  });

  const last = series[series.length - 1];
  const first = series[0];
  const bottomY = pad + innerH;
  const fillBase =
    series.length >= 2
      ? `${pts[0].split(",")[0]},${bottomY} ${pts.join(" ")} ${pts[pts.length - 1].split(",")[0]},${bottomY}`
      : "";

  return (
    <div className="plant-detail-modal__spark-wrap">
      <svg
        className="plant-detail-modal__spark-svg"
        viewBox="0 0 100 36"
        preserveAspectRatio="none"
        aria-hidden
      >
        <defs>
          <linearGradient
            id={`spark-fill-${gradId}`}
            x1="0"
            y1="0"
            x2="0"
            y2="1"
          >
            <stop
              offset="0%"
              stopColor="var(--color-mint)"
              stopOpacity="0.28"
            />
            <stop
              offset="100%"
              stopColor="var(--color-deep-teal)"
              stopOpacity="0.08"
            />
          </linearGradient>
        </defs>
        {series.length >= 2 ? (
          <>
            <polygon fill={`url(#spark-fill-${gradId})`} points={fillBase} />
            <polyline
              fill="none"
              stroke="var(--color-deep-teal)"
              strokeWidth="1.25"
              vectorEffect="non-scaling-stroke"
              points={pts.join(" ")}
            />
          </>
        ) : (
          <circle
            cx={pts[0].split(",")[0]}
            cy={pts[0].split(",")[1]}
            r="2.25"
            fill="var(--color-deep-teal)"
          />
        )}
      </svg>
      <div className="plant-detail-modal__spark-axis">
        <span>{first.year}</span>
        <span>{last.year}</span>
      </div>
      <p className="plant-detail-modal__spark-caption">
        Latest:{" "}
        <strong className="num">
          {(last.cf * 100).toLocaleString(undefined, {
            maximumFractionDigits: 1,
          })}
          %
        </strong>{" "}
        <span className="muted">({last.year})</span>
      </p>
    </div>
  );
}
