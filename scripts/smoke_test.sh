#!/usr/bin/env bash
# Smoke test for a running Job Tracker instance.
# Usage: BASE_URL=http://localhost:9000 ./scripts/smoke_test.sh
# BASE_URL defaults to http://localhost:9000 if unset.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:9000}"
BASE_URL="${BASE_URL%/}"  # strip trailing slash

pass=0
fail=0

check() {
  local label="$1"
  local condition="$2"
  if eval "$condition"; then
    echo "  PASS  $label"
    (( pass++ )) || true
  else
    echo "  FAIL  $label"
    (( fail++ )) || true
  fi
}

echo "Smoke test: $BASE_URL"
echo "---"

# --- /health ---
health_body=$(curl -sf --max-time 5 "$BASE_URL/health" 2>/dev/null || true)
check "/health returns 200" '[[ -n "$health_body" ]]'
check "/health status=ok"   '[[ "$(echo "$health_body" | python3 -c "import sys,json; print(json.load(sys.stdin).get(\"status\"))" 2>/dev/null)" == "ok" ]]'
check "/health database=ok" '[[ "$(echo "$health_body" | python3 -c "import sys,json; print(json.load(sys.stdin).get(\"database\"))" 2>/dev/null)" == "ok" ]]'

# --- root path reachable ---
root_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BASE_URL/" 2>/dev/null || echo "000")
check "/ reachable (200)" '[[ "$root_code" == "200" ]]'

echo "---"
echo "Passed: $pass  Failed: $fail"

(( fail == 0 ))
