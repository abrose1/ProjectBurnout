/**
 * Shorten noisy API / network errors for display.
 * @param {string} message
 */
export function shortenError(message) {
  if (!message || message.length < 180) return message;
  return `${message.slice(0, 180)}…`;
}
