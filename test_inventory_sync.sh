#!/usr/bin/env bash
set -euo pipefail
cd /opt/whatspricebot

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if [ -z "${INVENTORY_SYNC_TOKEN:-}" ]; then
  echo "ERROR: INVENTORY_SYNC_TOKEN is missing in /opt/whatspricebot/.env"
  echo "Run ./ensure_inventory_sync_token.sh first"
  exit 1
fi

URL="${1:-http://127.0.0.1:8090/api/sync_inventory}"
SAMPLE="${2:-sample_inventory.json}"

curl -sS -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-Inventory-Token: $INVENTORY_SYNC_TOKEN" \
  --data-binary "@$SAMPLE" | python3 -m json.tool
