# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is
A local-only, single-user job application tracker — FastAPI + Jinja2 + SQLite + Uvicorn. It runs bare-metal on one machine (or in a container, see below), bound to `127.0.0.1` only by default. There is no authentication and no multi-user support. Do not add either back.

Stack: FastAPI, Jinja2, SQLite, Bootstrap CDN, Uvicorn.

## Run it
`./start.sh` is the single entry point: it creates `.venv` on first run, installs `app/requirements.txt`, and starts Uvicorn on `127.0.0.1:9000`.

```bash
./start.sh             # port 9000 (default)
PORT=8080 ./start.sh   # override the port
```

Then open http://localhost:9000 — it goes straight to the dashboard (no login). Requires Python 3.12 (falls back to `python3` if 3.12 isn't on PATH).

Alternatively, run it with Docker (`docker compose up --build`) — see [README.md](README.md) for details. The container still only binds to `127.0.0.1` on the host.

## Test it
```bash
python3 -m pytest tests/
```
Run this before considering any change complete.

## Layout
- `start.sh` — single entry point: venv setup, dependency install, app start
- `app/requirements.txt` — pinned dependencies
- `app/main.py` — app factory, `/health`, Uvicorn entrypoint (localhost:9000)
- `app/config.py` — `.env` loading and `WEEKLY_TARGET`
- `app/db.py` — SQLite connection; database lives at `./db/job_tracker.db` (override with `DATABASE_PATH`)
- `app/migrations.py` — schema migrations applied at startup
- `app/queries.py` — all SQL, plus `normalize_application_form` (server-side form validation)
- `app/models.py` — status/source/work-mode enums and `APPLICATION_FIELDS`
- `app/csv_export.py` — CSV export serialization
- `app/routes/` — dashboard, applications, followups, export
- `templates/`, `static/` — Jinja2 views and CSS
- `tests/` — pytest suite
- `scripts/smoke_test.sh` — post-deploy smoke test against a running instance
- `db/` — runtime SQLite database (gitignored)
- `Dockerfile`, `docker-compose.yml` — optional container packaging

## Configuration
All optional; code defaults cover local use, so `.env` is not required.
- `DATABASE_PATH` — defaults to `./db/job_tracker.db`
- `PORT` — defaults to `9000`. Only takes effect as a **shell** environment variable read by `start.sh` (`PORT=8080 ./start.sh`) or by `docker-compose.yml`. Setting `PORT` inside `.env` has no effect on the `./start.sh` path, since `start.sh` reads `$PORT` before Python/`load_env_file()` ever runs.
- `WEEKLY_TARGET` — defaults to `25`

## Domain model

### Application fields
- id
- company
- role_title
- location
- work_mode
- source
- jd_url
- salary_min
- salary_max
- status
- job_description
- applied_date
- follow_up_date
- notes
- created_at
- updated_at

Salary fields are plain numbers (currency-agnostic) — this app doesn't assume a specific currency or compensation convention.

### Status values
- saved
- applied
- hr_screen
- tech_round
- final_round
- offer
- rejected
- withdrawn

## Scope

The app tracks job applications, follow-ups, job descriptions, and weekly application progress.

### Allowed change scope
- SQLite PRAGMAs (WAL, synchronous, busy_timeout, foreign_keys)
- Server-side validation in `normalize_application_form`
- Migration additions in `app/migrations.py`
- Environment variable additions in `.env.example` and `app/config.py`
- pytest test additions in `tests/`
- Documentation updates

### Constraints
This is intentionally a minimal, local-first tool. Do not add, even if asked:
- React, TypeScript, or any frontend build tool
- PostgreSQL, MySQL, or any non-SQLite database
- Authentication, OAuth, SSO, or multi-user support
- AI features, LLM calls, or job scraping
- Kanban boards, background workers, or email notifications
- nginx, reverse proxy, TLS, or any hosted/multi-tenant deployment tooling

### Working rules
1. Keep changes small and reviewable — one logical change at a time.
2. Reject out-of-scope changes (see Constraints).
3. Avoid unrelated edits in the same changeset.
4. Run `python3 -m pytest tests/` before considering a change done.
