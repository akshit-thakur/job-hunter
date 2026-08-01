# Job Tracker

A self-hosted, single-user job application tracker built with FastAPI, Jinja2, SQLite, Bootstrap CDN, and Uvicorn. Runs locally, bound to localhost only — no auth, no multi-user support, no hosted deployment.

## Features

- Add and edit job applications
- Track status, source, work mode, salary range (currency-agnostic), resume version, notes, and follow-up dates
- Dashboard metrics for weekly volume, funnel state, sources, locations, and work modes
- Follow-ups due page
- CSV export
- Compact quick-add clients for the macOS menu bar and Zen/Firefox

> **Note:** the UI loads Bootstrap CSS from a CDN ([base.html](templates/base.html)), so styling requires internet access on first load (and whenever the browser cache is cleared). The app itself has no other external dependencies and works fully offline otherwise.

## Run

Requires Python 3.12. The startup script is the single entry point — it creates the virtualenv on first run, installs dependencies, and starts the app:

```bash
./start.sh
```

Open:

```text
http://localhost:9000
```

Override the port with the `PORT` environment variable:

```bash
PORT=8080 ./start.sh
```

The app binds to `127.0.0.1`, so it is reachable only from this machine. There is no login — opening the URL goes straight to the dashboard.

## Run with Docker

Alternatively, run it in a container. This still only binds to `127.0.0.1` on the host, so it's reachable only from this machine — same security posture as the bare-metal setup.

```bash
docker compose up --build
```

Open http://localhost:9000. The SQLite database persists in `./db/job_tracker.db` across restarts. Docker uses the same `./start.sh` entry point as local runs, with container-specific environment values so Uvicorn binds correctly inside the container. The image also includes the Zen extension source and serves its ZIP package. Override the port by setting `PORT` before running compose, or by editing the port mapping in `docker-compose.yml`.

## Environment Variables

All optional; the defaults below cover local use, so a `.env` file is not required (copy `.env.example` to `.env` only if you want to override something).

- `DATABASE_PATH`: defaults to `./db/job_tracker.db`.
- `PORT`: defaults to `9000`. For `./start.sh`, this must be set as a shell environment variable (`PORT=8080 ./start.sh`) — setting it in `.env` has no effect, since `start.sh` reads `$PORT` before the app's `.env` loader runs. For Docker, set it before `docker compose up` (`PORT=8080 docker compose up --build`).
- `WEEKLY_TARGET`: target used to calculate "Remaining This Week". Defaults to `25`. Must be a positive integer.

## CSV Export

Use the navigation link or open:

```text
http://localhost:9000/export.csv
```

The exported filename is:

```text
job_applications_YYYYMMDD.csv
```

Rows are ordered by `updated_at` descending (most recently modified first), with `id` descending as the tiebreaker. CSV ordering is independent of the current list filters and sort.

## Smoke Test

Verifies that a running instance responds correctly on the health endpoint and root path.

```bash
chmod +x scripts/smoke_test.sh
BASE_URL=http://localhost:9000 ./scripts/smoke_test.sh
```

`BASE_URL` defaults to `http://localhost:9000` if not set.

Checks performed:

- `GET /health` returns HTTP 200 with `"status": "ok"` and `"database": "ok"`
- `GET /` returns HTTP 200

Exit 0 means all checks passed. Non-zero means at least one check failed — the output identifies which.

## JSON API (quick-add clients)

The same process also serves a small JSON API for the native and browser quick-add clients:

- `GET /stats` → `{ applied, interviewing, active, total, submitted_this_week, weekly_target, followups_due }`
- `POST /applications` → body `{ company, role, url?, status?, notes? }` creates a row (defaults `status` to `applied`)

Required and optional text values are trimmed by the API before they are stored.
The final two stats fields remain for compatibility with already-installed menu-bar clients.

## Zen / Firefox extension

The extension is a manual compact form. It does not read the current tab, inject content scripts, or prefill fields.

With the tracker running, download the package from:

```text
http://127.0.0.1:9000/extension/zen.zip
```

For a temporary personal installation:

1. Open `about:debugging` in Zen.
2. Choose **This Firefox** and **Load Temporary Add-on**.
3. Select the downloaded ZIP.

Use `Alt+Shift+J` on Windows/Linux or `Command+Shift+J` on macOS to open the form. The shortcut can be changed from the browser's extension-shortcut settings. Firefox-compatible browsers remove temporary add-ons when the browser restarts; persistent installation requires a Mozilla-signed package or a browser build configured to accept unsigned extensions.

The extension intentionally connects only to `http://127.0.0.1:9000`. Keep the default Docker port when using it.

## macOS menu-bar client

Open `macos/JobHunterBar/JobHunterBar.xcodeproj` in Xcode to develop, or install a standalone copy:

```bash
./macos/JobHunterBar/install.sh          # build → /Applications → launch
./macos/JobHunterBar/install.sh --login  # also open at login
```

It talks to `http://127.0.0.1:9000`. Keep the API up with `docker compose up -d`; the container runs through `./start.sh`, so the native client, extension, and Docker paths share one backend.

## Scope Boundaries

This is a local-first tool and intentionally does not include React, PostgreSQL, OAuth, authentication, multi-user support, job scraping, AI features, kanban boards, background workers, email notifications, or any hosted/multi-tenant deployment tooling.

## License

MIT — see [LICENSE](LICENSE).
