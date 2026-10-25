# Dashboard

Use Node 20.19+ (Node 22 is used in CI) and the repository's Python 3.10 environment.

```powershell
cd web
npm ci
npm run dev
```

Open the Local URL printed by Vite, usually `http://127.0.0.1:5173/`. All six pages
read the committed public exports. There is no backend server requirement. Hash
routes and a relative asset base support a future GitHub Pages project deployment.
No website has been deployed by this implementation step.

## Checks

```powershell
npm run check
npx playwright install chromium
npm run e2e
npm run audit
```

`check` runs ESLint, Prettier, strict TypeScript, Vitest with coverage, generated
schema validators, a production build and a 250KB total gzip JavaScript budget.
The repository's `make check` also runs it after the Python checks. `make setup`
now installs the locked frontend dependencies. `.npmrc` retains the npm 10 legacy
peer resolver used to create this lockfile; required React peers are explicit.

Runtime validators are generated from the Python-emitted draft-2020-12 JSON Schemas
before dev, type checks, unit tests and build. They do not evaluate schemas in the
browser. Generated validators stay ignored and regenerate after schema changes.
Complete bundle identity, timestamp and version are checked before rendering.
The loader caches only a verified in-memory update and clears failed requests.

Browser tests use the production build and bundled Chromium, with all data local.
Visual baselines are Windows/Chromium, matching the browser CI job. They cover all
six routes, both themes, desktop and 360px, for real and synthetic supported data.
Review screenshot changes before deliberately updating them with
`npm run e2e -- --update-snapshots`; subsequent normal runs compare against them.
Screenshots can vary by host rendering, so other platforms should run functional
tests with `npm run e2e -- --grep-invert visual` and use the Windows CI for visuals.

The performance audit serves the actual `dist` with gzip text responses, mirroring
compressed static hosting. It audits six real-data routes with Lighthouse's default
mobile simulation and requires 95 for performance, accessibility and best practices.
The audit launcher uses pinned Lighthouse 13.5.0 and an isolated npm-provided Node
22.23.4 runtime, so Node 20 remains sufficient for the app's normal workflow. Its
first run downloads those audit tools; later runs reuse npm's cache. The tool setup
is separate from the offline unit/browser tests. Detailed reports are ignored under
`lighthouse-results/`. Audit results depend on the host and served data.

## Data and usability

Production observations stay in `public/data/`. Refresh them with the Python
`tracker export` command at the repository root. The current 90-listing one-day
sample has honest unavailable index/model states; it never substitutes demo data.

Synthetic data under `tests/fixtures/` exercises supported charts and the calculator.
Twenty Python reference predictions are checked again in Python and TypeScript.
To intentionally regenerate them, run at the repository root:

```powershell
.venv/Scripts/python.exe -m scripts.generate_web_fixtures
```

The script never writes production exports. The six-week synthetic sample is not
Pakistan market evidence. Font files are served locally from the pinned licensed
Schibsted Grotesk package. Keyboard focus, skip navigation, reduced motion, chart
tables, labelled narrow-screen rows, dependent inputs and explicit errors are part
of the UI contract in [the design handoff](../docs/DASHBOARD.md).
