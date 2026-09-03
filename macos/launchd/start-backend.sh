#!/usr/bin/env bash
# Start the Job Tracker backend through Docker Compose.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$ROOT"
exec docker compose up -d --build
