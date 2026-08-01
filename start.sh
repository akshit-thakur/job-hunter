#!/usr/bin/env bash
# Single entry point for the Job Tracker.
# Creates the virtualenv (first run), installs dependencies, and starts the
# app on localhost.
#
# Usage:
#   ./start.sh                         # start on port 9000 (default)
#   PORT=8080 ./start.sh               # override the port
#   HOST=0.0.0.0 ./start.sh            # bind all interfaces (for containers)
#   JOB_TRACKER_SKIP_VENV=1 ./start.sh # use already-installed dependencies
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-9000}"
HOST="${HOST:-127.0.0.1}"
VENV_DIR=".venv"
SKIP_VENV="${JOB_TRACKER_SKIP_VENV:-0}"

if [[ "$SKIP_VENV" != "1" ]]; then
  # Pick a Python interpreter (prefer 3.12, fall back to python3).
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON=python3.12
  else
    PYTHON=python3
  fi

  # Create the virtualenv on first run.
  if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating virtual environment in $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  # Install dependencies only when requirements.txt has changed.
  HASH_FILE="$VENV_DIR/.requirements.sha256"
  if command -v sha256sum >/dev/null 2>&1; then
    CURRENT_HASH="$(sha256sum app/requirements.txt | cut -d' ' -f1)"
  else
    CURRENT_HASH="$(shasum -a 256 app/requirements.txt | cut -d' ' -f1)"
  fi
  if [[ ! -f "$HASH_FILE" || "$(cat "$HASH_FILE")" != "$CURRENT_HASH" ]]; then
    echo "Installing dependencies ..."
    pip install --quiet --upgrade pip
    pip install --quiet -r app/requirements.txt
    echo "$CURRENT_HASH" > "$HASH_FILE"
  fi
fi

# Start the app. exec so signals (Ctrl-C / docker stop) reach uvicorn directly.
echo "Starting Job Tracker on http://$HOST:$PORT"
exec uvicorn app.main:app --host "$HOST" --port "$PORT"
