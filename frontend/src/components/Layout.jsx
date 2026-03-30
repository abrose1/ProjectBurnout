import { Masthead } from "./Masthead";

export function Layout({ children }) {
  return (
    <div className="layout">
      <div className="layout__inner">
        <Masthead />
        <main className="layout__main">{children}</main>
      </div>
    </div>
  );
}
