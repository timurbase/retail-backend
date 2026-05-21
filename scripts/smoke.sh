#!/usr/bin/env bash
# Sprint 1 smoke test — exercises the full auth + onboarding flow.
# Reads OTP from a tail of dev SMS log (printed by services.py in dev).
set -euo pipefail

HOST=${HOST:-http://127.0.0.1:8000}
PHONE=${PHONE:-901234567}
STIR=${STIR:-301234567}
COMPANY=${COMPANY:-"Smoke MChJ"}
FULL_NAME=${FULL_NAME:-"Smoke User"}

echo "==> [1/5] send-otp register"
RESP=$(curl -fsS -X POST "$HOST/api/auth/send-otp/" \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"$PHONE\",\"purpose\":\"register\"}")
echo "    $RESP"

read -rp "    Paste OTP from server console: " OTP

echo "==> [2/5] verify-otp"
RESP=$(curl -fsS -X POST "$HOST/api/auth/verify-otp/" \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"$PHONE\",\"code\":\"$OTP\",\"purpose\":\"register\"}")
echo "    $RESP" | head -c 200; echo " ..."
ACCESS=$(echo "$RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')

echo "==> [3/5] register-store"
RESP=$(curl -fsS -X POST "$HOST/api/auth/register/" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"stir\":\"$STIR\",\"company_name\":\"$COMPANY\",\"full_name\":\"$FULL_NAME\"}")
echo "    $RESP" | head -c 200; echo " ..."
ACCESS=$(echo "$RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')

echo "==> [4/5] /api/company/ GET"
curl -fsS "$HOST/api/company/" -H "Authorization: Bearer $ACCESS"; echo

echo "==> [5/5] /api/company/ PATCH"
curl -fsS -X PATCH "$HOST/api/company/" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"director":"Aziz Karimov","email":"aziz@example.uz"}'
echo

echo "==> /api/audit-log/?limit=5"
curl -fsS "$HOST/api/audit-log/?limit=5" -H "Authorization: Bearer $ACCESS" \
  | python3 -m json.tool | head -40
