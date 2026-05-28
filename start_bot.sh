#!/usr/bin/env bash
set -e
cd /opt/whatspricebot

if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

export PORT="${PORT:-8090}"
export VERIFY_TOKEN="${VERIFY_TOKEN:-WhatsPrice2026}"
export ADMIN_TOKEN="${ADMIN_TOKEN:-admin2026}"
export PHARMACY_NAME="${PHARMACY_NAME:-صيدلية بدر البشرية}"
export ADMIN_PANEL_TITLE="${ADMIN_PANEL_TITLE:-لوحة إدارة صيدلية بدر البشرية}"

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^whatspricebot.service'; then
  systemctl restart whatspricebot
  sleep 2
  systemctl status whatspricebot --no-pager -l || true
else
  pkill -f "/opt/whatspricebot/app.py" || true
  pkill -f "gunicorn.*app:app" || true
  nohup /opt/whatspricebot/venv/bin/python /opt/whatspricebot/app.py > app.log 2>&1 &
  sleep 2
  tail -n 30 app.log
fi
