#!/usr/bin/env bash
set -e
cd /opt/whatspricebot
if [ -f ".env" ]; then set -a; source .env; set +a; fi
if [ -f "token_clean.txt" ] && [ -z "${WHATSAPP_TOKEN:-}" ]; then export WHATSAPP_TOKEN="$(cat token_clean.txt)"; fi
export PORT="${PORT:-8090}"
export VERIFY_TOKEN="${VERIFY_TOKEN:-WhatsPrice2026}"
export ADMIN_TOKEN="${ADMIN_TOKEN:-admin2026}"
pkill -f "/opt/whatspricebot/app.py" || true
nohup /opt/whatspricebot/venv/bin/python /opt/whatspricebot/app.py > app.log 2>&1 &
sleep 2
tail -n 30 app.log
