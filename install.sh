#!/usr/bin/env bash
set -e
cd /opt/whatspricebot
apt update -y
apt install -y python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m py_compile app.py vision.py text_ai.py admin_cli.py
echo "INSTALL_OK"
