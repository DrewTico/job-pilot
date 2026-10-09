# Job Pilot approval review

Run 5B is a read-only Pages Router workspace. Python remains the production
server and security authority. Decisions stay at `/`.

Use Node 24.21.0 and npm 11.19.0 (see `.nvmrc`). From this directory:

```sh
npm ci --ignore-scripts
npm run lint
npm run typecheck
npm test
npm run build
```

The build disables Next telemetry, exports to ignored `out/`, then packages only
the root workspace's required files into ignored
`../src/job_agent/dashboard/ui_build/`. Do not deploy `out/` or `.next/` directly.
Do not run `next start` in production. No scripts need installation lifecycle hooks.

The existing approval app factory loads the complete manifest once per process.
`/ui` is available only when a valid packaged artifact is installed before
process creation. Nothing in the build starts or restarts the production service.
Operator delivery/restart stays a separate reviewed step. This milestone proves
source-checkout delivery at that fixed artifact path. Wheel distribution of
generated UI assets is deferred; do not assume gitignored build output is
included in a Python wheel.

For synthetic visual development only:

```sh
npm run dev
```

Visit the loopback development server's `/ui/demo/`. Its fictional data has a
prominent synthetic banner; the fixture reader makes no API requests. The Next
development server is **not** the protected production deployment and its dev
headers are not CSP evidence. The protected `/ui/demo/` route, demo HTML and
fixture-specific bundle are deliberately unavailable. Browser evidence comes
from the actual production export served by Python under its unchanged CSP.

Refresh public contracts or fictional fixtures from the repository root:

```sh
.venv/bin/python frontend/scripts/generate-contracts.py
.venv/bin/python frontend/scripts/generate-fixtures.py
```

These scripts load DTO definitions only. They do not read settings, private data,
providers or storage. Contract tests detect drift against Pydantic.

Validation from the repository root uses the existing Python Playwright setup:

```sh
.venv/bin/pytest -q tests/test_frontend_delivery.py tests/test_frontend_proof.py tests/test_frontend_ui_dom.py
```

On this managed environment, Node build/test subprocesses, Chromium, and threaded
ASGI tests require the established outside-sandbox execution approval. Browser
fixtures abort every resource outside their assigned loopback origin and forbid
backend provider/employer calls. All SQLite use is temporary test storage.

Rollback: remove the packaged `ui_build/manifest.json` (or omit the artifact), then
recreate the approval app through the existing operator-managed restart path.
`/ui` fails closed with 404 and `/` and protected APIs stay available. Loaded
bytes are immutable in memory, so removal alone does not change a running app.
No database, schema, domain, authentication, Serve or systemd rollback is needed.
