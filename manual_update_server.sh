#!/usr/bin/env bash
set -e

cd /opt/whatspricebot

echo "BACKUP..."
tar -czf /opt/whatspricebot_before_update_$(date +%Y%m%d_%H%M%S).tar.gz \
  --exclude='/opt/whatspricebot/venv' \
  --exclude='/opt/whatspricebot/__pycache__' \
  /opt/whatspricebot

python3 -m py_compile app.py vision.py admin_cli.py
./start_bot.sh

echo "UPDATE_OK"
