# Job Tracker

A self-hosted, single-user job application tracker built with FastAPI, Jinja2, SQLite, Bootstrap CDN, and Uvicorn. Runs locally, bound to localhost only — no auth, no multi-user support, no hosted deployment.

## Features

- Add and edit job applications
- Track status, source, work mode, salary range (currency-agnostic), job description text, notes, and follow-up dates
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

Run the backend in a container for normal use. This binds only to `127.0.0.1` on the host, so it's reachable only from this machine — same security posture as the bare-metal setup.

```bash
docker compose up -d --build
```

Open http://localhost:9000. The SQLite database persists in `./db/job_tracker.db` across restarts. Docker Compose runs `./start.sh` inside the container, with container-specific environment values so Uvicorn binds correctly inside Docker. The Compose service uses `restart: unless-stopped`, so the backend keeps running without a terminal window. The image also includes the Zen extension source and serves its ZIP package. Override the port by setting `PORT` before running compose, or by editing the port mapping in `docker-compose.yml`.

For development, `./start.sh` still runs the app directly on the host.

## Run at Login on macOS

Install the menu-bar app once:

```bash
./macos/JobHunterBar/install.sh
```

Then install the per-user LaunchAgents:

```bash
./macos/launchd/install.sh
```

This is the macOS launchd equivalent of a user-level systemd setup:

- `local.job-hunter.backend` runs `docker compose up -d` through `macos/launchd/start-backend.sh`.
- `local.job-hunter.menubar` runs `/Applications/JobHunterBar.app/Contents/MacOS/JobHunterBar` and keeps it alive.

Uninstall the LaunchAgents with:

```bash
./macos/launchd/install.sh --uninstall
```

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

## Import / Sync

Use **Applications → Import** to bulk import or sync rows from CSV or JSON.

The CSV importer accepts the app's own export and simpler external CSVs. It updates an existing application by `id` when present; otherwise it matches by `company + role_title`. Rows with no match are created.

Recognized columns include:

```text
company, role_title, role, location, work_mode, mode, source, jd_url, url,
salary_min, salary_max, status, job_description, description, applied_date,
follow_up_date, notes
```

When `source` is omitted or set to `other`, the importer infers it from the job URL using the same static host dictionary as quick-add.

JSON import accepts either one object or an array of objects. It supports scraper-shaped fields such as:

```text
job_id, title, company, location, work_type, status, timestamp, applied_date,
job_url, scraped_at
```

For LinkedIn-style applied-job records, explicit `applied_date` values or `timestamp` values like `Applied 3mo ago` are treated as an application signal, while the original listing status is preserved in notes. `work_type` values such as `Remote` map to work mode. Concatenated titles such as `AI Data EngineerMultiBank Group` are split into role and company when a recognizable company suffix is present.

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
- `POST /applications` → body `{ company, role, url?, status?, notes?, job_description?, source?, work_mode?, location?, follow_up_date? }` creates a row (defaults `status` to `applied`)

Required and optional text values are trimmed by the API before they are stored.
If `source` is omitted or `other`, the API infers a source from common job posting hosts such as LinkedIn, Indeed, Naukri, Greenhouse, Lever, Ashby, and Workday.

## Zen / Firefox extension

The extension is a compact quick-add form. It reads the active tab URL and title when opened, prefills draft fields, and sends structured quick-add fields to the local API. It does not inject content scripts or scrape page content.

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

The menu-bar form can use the active browser tab for autofill. Safari and common Chromium-family browsers expose tab URL/title through macOS Automation; macOS may ask for permission the first time. The URL is sent to the backend, which infers the application source from common job-board and ATS domains.

## Scope Boundaries

This is a local-first tool and intentionally does not include React, PostgreSQL, OAuth, authentication, multi-user support, job scraping, AI features, kanban boards, background workers, email notifications, or any hosted/multi-tenant deployment tooling.

## License

MIT — see [LICENSE](LICENSE).
