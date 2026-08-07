#!/usr/bin/env bash
# The four smoke assertions, from anywhere with curl — the between-deploys detector
# Corrections #5 and #6 lacked. Twice the live URL served a pre-auth Phase 0 image
# and nothing noticed until a human opened it; the smoke test closes the door at
# deploy time, this closes it between deploys. Scheduled by
# .github/workflows/deployed-probe.yml; runnable by hand from any machine.
#
# Uses the published read-only demo account (README "Signing in"), so it needs no
# secret anywhere — a probe that needs a credential store is a probe that stops
# running when the store moves.
set -euo pipefail

URL="${PROBE_URL:-https://hardware-hub-production-24b7.up.railway.app}"
COOKIES="$(mktemp)"
trap 'rm -f "$COOKIES"' EXIT

fail() {
  echo "PROBE FAIL: $1" >&2
  exit 1
}

# 1. No public read surface (ADR-0006). A 200 here is the pre-auth rollback —
#    the exact regression that served restricted fields publicly, twice.
code=$(curl -sS -o /dev/null -w '%{http_code}' "$URL/api/hardware")
[ "$code" = "401" ] || fail "anonymous GET /api/hardware answered $code, expected 401 — a 200 means a pre-auth image is live (AI_LOG Correction #6)"

# 2. The health route exists. It postdates Phase 0, so a 404 is an old image.
code=$(curl -sS -o /dev/null -w '%{http_code}' "$URL/api/health")
[ "$code" = "200" ] || fail "GET /api/health answered $code, expected 200 — the route did not exist in early images, so a 404 is a rollback"

# 3. Login works with the published demo credential.
code=$(curl -sS -o /dev/null -w '%{http_code}' -c "$COOKIES" \
  -X POST "$URL/api/login" -H 'Content-Type: application/json' \
  -d '{"email":"demo@booksy.com","password":"hardware-hub-demo"}')
[ "$code" = "200" ] || fail "demo login answered $code, expected 200 — either auth regressed or the demo account is gone (README: Restoring the demo)"

# 4. The signed-in inventory is non-empty — the volume is mounted and seeded.
count=$(curl -sS -b "$COOKIES" "$URL/api/hardware" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
[ "$count" -gt 0 ] 2>/dev/null || fail "signed-in inventory came back empty or unreadable — the volume is missing or the seed guard misfired"

echo "probe ok: anonymous 401, health 200, demo login 200, $count items"
