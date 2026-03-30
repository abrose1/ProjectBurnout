Burnout frontend — static export for prototyping elsewhere
============================================================

Files:
  index.html   — shell; mounts the React app on #root
  styles.css   — production CSS bundle (from Vite build)
  bundle.js    — production JS bundle (React app, ES module)
  favicon-flame-128.png  — tab / apple-touch icon (128×128)
  flame-icon-no-bg.png   — 32×32; bundle cursor URL if you copy static CSS that references it

Regenerate from the repo (after `npm run build`):
  From frontend/: the built assets live in dist/assets/ with hashed names.
  Copy the latest .css and .js from dist/assets/ to styles.css and bundle.js,
  or run:  npm run build && cp dist/assets/index-*.css platform-export/styles.css
  (adjust the glob/hash to match the current build output).

Runtime:
  This is a client-side SPA. It expects VITE_API_URL at build time (baked into
  the bundle). To point at an API when testing this folder, rebuild with
  VITE_API_URL set in frontend/.env, then re-copy bundle.js.

Serve the folder over HTTP (e.g. npx serve platform-export) so ES modules load;
opening index.html as file:// may block modules in some browsers.
