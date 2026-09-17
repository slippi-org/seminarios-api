#!/usr/bin/env bash
# Verify a running Seminarios API end to end, from outside it.
#
#   ./smoke.sh http://ag-rpi5:9286 PLAYER-TOKEN [GM-TOKEN]
#
# Phase 2 wants this run against https://seminarios-api.slippi.org from a
# network that is not yours. With a GM token it also proves that a player cannot
# see gm-visibility rows -- the check that actually matters.
set -uo pipefail

BASE="${1:?usage: smoke.sh <base-url> <player-token> [gm-token]}"
PLAYER="${2:?a player token is required}"
GM="${3:-}"
API="$BASE/api/v1"
PASS=0; FAIL=0
STAMP="smoke-$(date +%s)"

ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
body() { curl -s "$@"; }

echo "== $BASE =="

[ "$(code "$BASE/healthz")" = 200 ] \
  && ok "/healthz answers unauthenticated" || bad "/healthz"

[ "$(code -H 'Authorization: Bearer NOPE-NOPE-NOPE-NOPE' "$API/me")" = 401 ] \
  && ok "a bad token is rejected" || bad "bad token was not rejected"

[ "$(code "$API/state")" = 401 ] \
  && ok "reads require a token" || bad "unauthenticated read was allowed"

me="$(body -H "Authorization: Bearer $PLAYER" "$API/me")"
echo "$me" | grep -q '"role"' \
  && ok "/me: $(echo "$me" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["player"]["display_name"], "/", d["role"])')" \
  || bad "/me did not return a player"

# The token as a player would actually type it: lowercase, spaces for dashes.
spoken="$(printf %s "$PLAYER" | tr 'A-Z' 'a-z' | tr '-' ' ')"
[ "$(code -H "Authorization: Bearer $spoken" "$API/me")" = 200 ] \
  && ok "token normalization accepts the spoken form" || bad "normalization"

roster="$(body -H "Authorization: Bearer $PLAYER" "$API/roster")"
echo "$roster" | grep -q '"players"' && ! echo "$roster" | grep -q token_hash \
  && ok "/roster lists players without secrets" || bad "/roster"

evt="evt_$STAMP"
c=$(code -X POST "$API/events" -H "Authorization: Bearer $PLAYER" \
      -H 'Content-Type: application/json' \
      -d "{\"id\":\"$evt\",\"place_id\":\"12_market\",\"day\":1620032,\"time_of_day\":\"evening\",\"text\":\"smoke test $STAMP\",\"visibility\":\"party\"}")
[ "$c" = 201 ] && ok "POST /events -> 201" || bad "POST /events -> $c"

[ "$(code -X POST "$API/events" -H "Authorization: Bearer $PLAYER" \
      -H 'Content-Type: application/json' \
      -d "{\"id\":\"$evt\",\"place_id\":\"12_market\",\"day\":1620032,\"text\":\"replay\",\"visibility\":\"party\"}")" = 200 ] \
  && ok "replayed POST is idempotent (200)" || bad "replay was not idempotent"

[ "$(code -X POST "$API/events" -H "Authorization: Bearer $PLAYER" \
      -H 'Content-Type: application/json' \
      -d "{\"id\":\"${evt}_forge\",\"place_id\":\"12_market\",\"day\":1620032,\"text\":\"forged\",\"visibility\":\"gm\"}")" = 403 ] \
  && ok "a player cannot create a gm row" || bad "a player CREATED a gm row"

body -H "Authorization: Bearer $PLAYER" "$API/state" | grep -q "$STAMP" \
  && ok "the event is readable in /state" || bad "event missing from /state"

[ "$(code -X DELETE "$API/events/$evt" -H "Authorization: Bearer $PLAYER")" = 200 ] \
  && ok "soft delete" || bad "delete"

if [ -n "$GM" ]; then
  sec="evt_${STAMP}_secret"
  curl -s -o /dev/null -X POST "$API/events" -H "Authorization: Bearer $GM" \
    -H 'Content-Type: application/json' \
    -d "{\"id\":\"$sec\",\"place_id\":\"23_red-light\",\"day\":1620032,\"text\":\"GM ONLY $STAMP\",\"visibility\":\"gm\"}"
  if body -H "Authorization: Bearer $PLAYER" "$API/state" | grep -q "GM ONLY"; then
    bad "!! a gm row LEAKED to a player !!"
  else
    ok "gm rows are invisible to a player"
  fi
  body -H "Authorization: Bearer $GM" "$API/state" | grep -q "GM ONLY" \
    && ok "the gm sees their own row" || bad "gm cannot see their own row"
  curl -s -o /dev/null -X DELETE "$API/events/$sec" -H "Authorization: Bearer $GM"
else
  echo "  (skipped gm-visibility checks -- pass a GM token as \$3)"
fi

echo
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
