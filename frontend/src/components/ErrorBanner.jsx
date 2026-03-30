import { shortenError } from "../utils/formatError";

export function ErrorBanner({ title, message, onRetry, retryLabel = "Retry" }) {
  return (
    <div
      className="banner banner--error"
      role="alert"
      aria-live="polite"
    >
      <div className="banner__title">{title}</div>
      <p className="banner__body">{shortenError(message)}</p>
      {onRetry && (
        <button type="button" className="btn btn--secondary" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  );
}
