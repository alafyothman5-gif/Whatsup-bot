#!/usr/bin/env bash
set -euo pipefail
cd /opt/whatspricebot

echo "1) Backup current project..."
tar -czf "/opt/whatspricebot_before_inventory_sync_$(date +%Y%m%d_%H%M%S).tar.gz" \
  --exclude='/opt/whatspricebot/venv' \
  --exclude='/opt/whatspricebot/__pycache__' \
  --exclude='/opt/whatspricebot/backups' \
  /opt/whatspricebot

echo "2) Ensure inventory sync token..."
./ensure_inventory_sync_token.sh

echo "3) Install/check dependencies..."
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

echo "4) Compile Python files..."
python3 -m py_compile app.py vision.py text_ai.py admin_cli.py

echo "5) Restart service..."
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^whatspricebot.service'; then
  systemctl restart whatspricebot
  sleep 2
  systemctl status whatspricebot --no-pager -l || true
else
  ./start_bot.sh
fi

echo "6) Health check..."
curl -s http://127.0.0.1:8090/health && echo

echo "DEPLOY_INVENTORY_SYNC_OK"
