#!/usr/bin/env bash
set -euo pipefail
cd /opt/whatspricebot

if [ ! -f .env ]; then
  echo "ERROR: /opt/whatspricebot/.env not found"
  exit 1
fi

if grep -q '^INVENTORY_SYNC_TOKEN=' .env; then
  echo "INVENTORY_SYNC_TOKEN already exists in .env"
else
  TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  cp .env ".env.before_inventory_sync_$(date +%Y%m%d_%H%M%S)"
  printf '\nINVENTORY_SYNC_TOKEN=%s\nMAX_SYNC_PRODUCTS=50000\nALLOW_EMPTY_INVENTORY_SYNC=false\n' "$TOKEN" >> .env
  echo "INVENTORY_SYNC_TOKEN added to .env"
fi
