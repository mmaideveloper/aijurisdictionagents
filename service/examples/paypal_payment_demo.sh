#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8088}"

printf 'Creating fake PayPal payment...\n'
create_response=$(curl -sS -X POST "$BASE_URL/paypal/payments" \
  -H 'content-type: application/json' \
  -d '{"amount":59.99,"currency":"eur","payerEmail":"buyer@example.com","description":"Subscription renewal"}')

printf '%s\n' "$create_response"

payment_id=$(printf '%s' "$create_response" | sed -n 's/.*"id": "\(PAY-[^"]*\)".*/\1/p' | head -n 1)

if [[ -z "$payment_id" ]]; then
  printf 'Unable to parse payment id from response.\n' >&2
  exit 1
fi

printf '\nFetching payment %s...\n' "$payment_id"
curl -sS "$BASE_URL/paypal/payments/$payment_id"

printf '\n\nExecuting payment %s...\n' "$payment_id"
curl -sS -X POST "$BASE_URL/paypal/payments/$payment_id/execute"

printf '\n\nDone.\n'
