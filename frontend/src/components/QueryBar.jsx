import { useCallback, useEffect, useId, useState } from "react";
import { useNlQuery } from "../hooks/useQuery";
import { apiFiltersToState, DEFAULT_PLANT_FILTERS } from "../utils/plantFilters";
import { getApiBase } from "../utils/api";

const WIDE_LAYOUT_QUERY = "(min-width: 640px)";

function useWideLayout() {
  const [wide, setWide] = useState(() =>
    typeof window !== "undefined"
      ? window.matchMedia(WIDE_LAYOUT_QUERY).matches
      : true
  );

  useEffect(() => {
    const mq = window.matchMedia(WIDE_LAYOUT_QUERY);
    const sync = () => setWide(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  return wide;
}

const EXAMPLES = [
  "Texas plants that will be unprofitable for at least 5 years",
  "Last gas plants to retire in PJM",
  "All PacifiCorp Plants",
];

/**
 * @param {{
 *   onFiltersChange: (f: typeof DEFAULT_PLANT_FILTERS) => void;
 *   onNlMessage: (msg: string | null, opts?: { fallback?: boolean; variant?: 'success' | 'warning' }) => void;
 *   interpretation: { message: string; variant: string; fallback: boolean } | null;
 * }} props
 */
export function QueryBar({
  onFiltersChange,
  onNlMessage,
  interpretation,
}) {
  const { submit, loading, error, clearError } = useNlQuery();
  const [text, setText] = useState("");
  const rootId = useId();
  const wideLayout = useWideLayout();
  const missingBase = getApiBase() === "";

  const fieldProps = {
    id: `${rootId}-input`,
    className: "query-bar__input",
    placeholder:
      "e.g. Large coal plants in the southeast ranked by retirement year",
    value: text,
    "aria-describedby": interpretation ? `${rootId}-nl-result` : undefined,
    onChange: (e) => setText(e.target.value),
    disabled: missingBase || loading,
    autoComplete: "off",
    spellCheck: false,
  };

  const runSearch = useCallback(
    async (queryOverride) => {
      clearError();
      const useString =
        typeof queryOverride === "string" && queryOverride.trim() !== "";
      const q = useString ? queryOverride.trim() : text.trim();
      if (useString) {
        setText(queryOverride.trim());
      }
      const result = await submit(q);
      if (!result) {
        onNlMessage(null);
        return;
      }
      if (result.filters_applied) {
        onFiltersChange(apiFiltersToState(result.filters_applied));
        onNlMessage(result.message, {
          fallback: result.fallback,
          variant: "success",
        });
      } else {
        onNlMessage(result.message, { variant: "warning" });
      }
    },
    [submit, text, onFiltersChange, onNlMessage, clearError]
  );

  const clearQuery = useCallback(() => {
    setText("");
    clearError();
    onFiltersChange({ ...DEFAULT_PLANT_FILTERS });
    onNlMessage(null);
  }, [clearError, onFiltersChange, onNlMessage]);

  return (
    <section
      className="query-bar"
      aria-labelledby={`${rootId}-heading`}
    >
      <h3 id={`${rootId}-heading`} className="query-bar__heading">
        Ask in your own words
      </h3>
      <div className="query-bar__row">
        <label htmlFor={`${rootId}-input`} className="visually-hidden">
          Natural language search
        </label>
        {wideLayout ? (
          <input
            type="search"
            {...fieldProps}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                runSearch();
              }
            }}
          />
        ) : (
          <textarea
            {...fieldProps}
            rows={2}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                runSearch();
              }
            }}
          />
        )}
        <div className="query-bar__actions">
          <button
            type="button"
            className="btn btn--primary query-bar__submit"
            onClick={() => runSearch()}
            disabled={missingBase || loading || !text.trim()}
          >
            {loading ? "Searching…" : "Search"}
          </button>
          <button
            type="button"
            className="btn btn--ghost query-bar__clear"
            onClick={clearQuery}
            disabled={loading}
          >
            Clear
          </button>
        </div>
      </div>

      {missingBase && (
        <p className="query-bar__banner query-bar__banner--warn muted">
          Set <code className="inline-code">VITE_API_URL</code> to use search.
        </p>
      )}

      {error && (
        <div className="query-bar__banner query-bar__banner--error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn--ghost btn--tiny" onClick={clearError}>
            Dismiss
          </button>
        </div>
      )}

      <div className="query-bar__examples" aria-label="Example searches">
        <span className="muted query-bar__examples-label">Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            className="query-bar__pill"
            onClick={() => runSearch(ex)}
            disabled={loading || missingBase}
          >
            {ex}
          </button>
        ))}
      </div>

      {interpretation && (
        <div
          className={`query-bar__interpretation query-bar__interpretation--${interpretation.variant}`}
          role="status"
          aria-live="polite"
        >
          <div className="query-bar__interpretation-header">
            <span className="query-bar__interpretation-label">
              How we filtered
            </span>
            {interpretation.fallback && (
              <span className="query-bar__interpretation-notice">Notice</span>
            )}
          </div>
          <p
            id={`${rootId}-nl-result`}
            className="query-bar__interpretation-text"
          >
            {interpretation.message}
          </p>
        </div>
      )}
    </section>
  );
}
