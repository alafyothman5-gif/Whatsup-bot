# WhatsPriceBot V2

بوت واتساب أسعار وتجربة منتجات، مبني على WhatsApp Cloud API.

## الموجود حاليًا

- Flask webhook يعمل على `/webhook`
- استقبال رسائل Meta Webhook
- بحث في `products.json`
- رد بالسعر والتوفر
- حفظ الرسائل غير المفهومة في `pending_reviews.json`
- حفظ الطلبات في `orders.json`
- دعم صور مبدئي: يحولها للمراجعة
- أداة إدارة من التيرمنل `admin_cli.py`
- اختبار محلي `test_v2.py`

## ملفات مهمة

- `app.py`: السيرفر والبوت
- `admin_cli.py`: إدارة المنتجات والأسماء البديلة والطلبات
- `products.json`: المنتجات والأسعار
- `start_bot.sh`: تشغيل البوت
- `save_token_clean.sh`: حفظ توكن واتساب محليًا
- `.env.example`: مثال متغيرات التشغيل

## تشغيل محلي/سيرفر

```bash
cd /opt/whatspricebot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m py_compile app.py admin_cli.py
./start_bot.sh
```

## حفظ التوكن

```bash
./save_token_clean.sh
```

الصق التوكن ثم اكتب `END` في سطر جديد.

## اختبار

```bash
python3 test_v2.py
cat send_log.txt
```

إذا ظهر `Account not registered` فهذا بسبب رقم Meta التجريبي، وليس مشكلة في الكود. الحل النهائي هو ربط رقم واتساب حقيقي في Meta.

## أوامر الإدارة

عرض المنتجات:

```bash
python3 admin_cli.py products
```

إضافة منتج:

```bash
python3 admin_cli.py add --id iphone_16 --name "iPhone 16" --price "6000 د.ل" --stock "متوفر" --aliases "ايفون 16,iphone 16"
```

إضافة اسم بديل:

```bash
python3 admin_cli.py alias --product s24_ultra --alias "سامسونق الترا"
```

عرض المراجعات:

```bash
python3 admin_cli.py pending
```

ربط pending بمنتج وتعليم البوت:

```bash
python3 admin_cli.py resolve --pending PENDING_ID --product s24_ultra
```

عرض الطلبات:

```bash
python3 admin_cli.py orders
```

## ملاحظات أمنية

لا ترفع الملفات التالية إلى GitHub:

- `token_clean.txt`
- `.env`
- `webhook_log.txt`
- `send_log.txt`
- `pending_reviews.json`
- `orders.json`

لذلك موجودة في `.gitignore`.
