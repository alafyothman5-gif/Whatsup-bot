#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  source .env
  set +a
elif [ -f token_clean.txt ]; then
  export WHATSAPP_TOKEN="$(cat token_clean.txt)"
  export PHONE_NUMBER_ID="${PHONE_NUMBER_ID:-1048608088345554}"
  export VERIFY_TOKEN="${VERIFY_TOKEN:-WhatsPrice2026}"
fi

pkill -f "$(pwd)/app.py" || true
nohup ./venv/bin/python app.py > app.log 2>&1 &
sleep 2
tail -n 30 app.log
