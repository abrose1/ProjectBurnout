/**
 * Site intro — reorder the blocks below to change reading order; styles stay in global.css (.masthead*).
 */
export function Masthead() {
  return (
    <header className="masthead">
      <div className="masthead__brand">
        <h1 className="masthead__title">Burnout</h1>
      </div>
      <h2 className="masthead__headline">
        Which Power Plants Will Become Unprofitable Before They Close?
      </h2>
      <p className="masthead__lede">
        Many US coal and gas plants are projected to become unprofitable years before
        they&apos;ll actually shut down — locked in by contracts, debt, and regulation.
        Explore which plants are most at risk.
      </p>
    </header>
  );
}
