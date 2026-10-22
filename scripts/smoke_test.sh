#!/usr/bin/env bash
# Post-deploy smoke test for a running Aegis API (used by CI and after every deploy).
#
#   scripts/smoke_test.sh http://localhost:8000 "$AEGIS_API_KEY"
#   scripts/smoke_test.sh https://aegis.example.com "$AEGIS_API_KEY"
#
# Checks: health, API key enforcement, and that HITL approvals succeed repeatedly
# (with several workers/pods this fails unless shared Postgres state is configured).
set -euo pipefail

BASE_URL="${1:?usage: smoke_test.sh <base-url> [api-key] [hitl-rounds]}"
API_KEY="${2:-}"
ROUNDS="${3:-5}"
KEY_HEADER=()
[[ -n "$API_KEY" ]] && KEY_HEADER=(-H "X-API-Key: ${API_KEY}")

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "1. Waiting for ${BASE_URL}/health"
for _ in $(seq 1 30); do
  curl -fsS "${BASE_URL}/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "${BASE_URL}/health" | grep -q HEALTHY || fail "health check"

if [[ -n "$API_KEY" ]]; then
  echo "2. /v1 rejects requests without the API key"
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/v1/rag/search" \
    -H "Content-Type: application/json" -d '{"query":"oom"}')
  [[ "$code" == "401" ]] || fail "expected 401 without key, got ${code}"
fi

echo "3. HITL approve round-trips (${ROUNDS}x)"
for i in $(seq 1 "$ROUNDS"); do
  thread=$(curl -fsS -X POST "${BASE_URL}/v1/agent/incidents" "${KEY_HEADER[@]}" \
    -H "Content-Type: application/json" \
    -d '{"service_name":"rag-retrieval","description":"CUDA OOM critical"}' |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["thread_id"])')
  status=$(curl -fsS -X POST "${BASE_URL}/v1/agent/incidents/${thread}/decision" "${KEY_HEADER[@]}" \
    -H "Content-Type: application/json" -d '{"approved":true,"reviewer":"smoke-test"}' |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])') ||
    fail "approval ${i} failed (another worker/pod did not know thread ${thread})"
  [[ "$status" == "COMPLETED" ]] || fail "approval ${i} ended in status ${status}"
done

echo "OK: all smoke checks passed"
