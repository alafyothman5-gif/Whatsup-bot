# WhatsPriceBot Vision Fallback

نسخة بوت واتساب أسعار مع قراءة صور باستخدام fallback:
1. Gemini key 1
2. Gemini key 2
3. OpenRouter
4. Cloudflare Workers AI
5. xAI / Grok

لا ترفع `.env` أو التوكنات إلى GitHub.

## التشغيل
```bash
cd /opt/whatspricebot
chmod +x install.sh start_bot.sh save_token_clean.sh manual_update_server.sh
./install.sh
./start_bot.sh
```

## المفاتيح
انسخ `.env.example` إلى `.env` وضع مفاتيحك هناك:
```bash
cp .env.example .env
nano .env
```

## طريقة الصور
صورة واتساب → تنزيل من Meta → Gemini1 → Gemini2 → OpenRouter → Cloudflare → Grok → بحث في products.json → رد بالسعر أو pending.
