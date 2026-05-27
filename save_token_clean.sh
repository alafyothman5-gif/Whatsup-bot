#!/usr/bin/env bash
set -e
cd /opt/whatspricebot
echo "الصق WHATSAPP_TOKEN كامل الآن. بعد ما تخلص اكتب END وحدها في سطر جديد."
rm -f token_raw.txt token_clean.txt
while IFS= read -r line; do
  if [ "$line" = "END" ]; then break; fi
  printf "%s" "$line" >> token_raw.txt
done
TOKEN="$(tr -d '\r\n \t' < token_raw.txt)"
if [ -z "$TOKEN" ]; then echo "TOKEN_EMPTY"; exit 1; fi
printf "%s" "$TOKEN" > token_clean.txt
chmod 600 token_clean.txt
echo "TOKEN_LENGTH=$(wc -c < token_clean.txt)"
