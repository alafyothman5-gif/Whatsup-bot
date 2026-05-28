# WhatsPriceBot V4.3 Inventory Sync Safe

نسخة نظيفة من بوت واتساب للمحال والصيدليات، مع أول خطوة رسمية لربط المخزون الخارجي بأمان.

## الموجود في هذه النسخة

- لوحة أدمن ثابتة بدون Auto Refresh مزعج.
- Inbox للطلبات التي تحتاج رد.
- إرسال رد للزبون من لوحة الأدمن.
- إضافة وتعديل المنتجات من اللوحة.
- سعر الشريط، سعر العلبة، عدد الشرائط، الكمية، والصلاحية.
- تحويل الأسئلة الطبية والروشتات للأدمن.
- Vision AI للصور مع تحويل أي شك للأدمن.
- Text AI Fallback: إذا فشل البحث المحلي، يحاول الذكاء الاصطناعي استخراج اسم المنتج فقط من الرسالة، ثم يرد من `products.json` بدون اختراع سعر.
- API آمن لاستقبال المخزون من برنامج خارجي لاحقًا.
- Backup تلقائي لـ `products.json` قبل كل مزامنة.
- Validation يمنع استبدال المخزون بملف فارغ أو تالف.
- حالة آخر مزامنة تظهر في لوحة الأدمن و `/health`.

## لوحة الأدمن

```text
/admin?token=admin2026
```

## API مزامنة المخزون

Endpoint:

```text
POST /api/sync_inventory
```

الحماية:

```text
X-Inventory-Token: INVENTORY_SYNC_TOKEN
```

أو:

```text
Authorization: Bearer INVENTORY_SYNC_TOKEN
```

شكل JSON المقبول:

```json
{
  "source": "WaselBot Scanner",
  "client_id": "badr_pharmacy",
  "mode": "replace",
  "products": [
    {
      "id": "congestal_box",
      "category": "أدوية برد",
      "name": "Congestal",
      "barcode": "622300000001",
      "price_strip": "5 د.ل",
      "price_box": "30 د.ل",
      "strips_count": "6",
      "quantity": "20",
      "expiry_date": "2027-05",
      "aliases": ["congestal", "كونجستال", "كونجستال اقراص"]
    }
  ]
}
```

## ملفات مهمة

- `products.json`: ملف المنتجات الحالي الذي يقرأه البوت.
- `sample_inventory.json`: ملف اختبار للمزامنة.
- `inventory_sync_status.json`: حالة آخر مزامنة، ينشأ تلقائيًا.
- `inventory_sync.log`: سجل المزامنة، ينشأ تلقائيًا.
- `backups/`: نسخ احتياطية تلقائية من المنتجات، ينشأ تلقائيًا.

## تثبيت على السيرفر

بعد رفع الملفات إلى GitHub أو نسخها إلى `/opt/whatspricebot`، شغل:

```bash
cd /opt/whatspricebot && chmod +x *.sh && ./deploy_inventory_sync_v1.sh
```

السكريبت سيعمل:

1. Backup للمشروع الحالي.
2. إنشاء `INVENTORY_SYNC_TOKEN` داخل `.env` إذا غير موجود.
3. تثبيت المتطلبات.
4. فحص `py_compile`.
5. Restart للخدمة.
6. Health check.

## اختبار المزامنة محليًا على السيرفر

بعد التشغيل:

```bash
cd /opt/whatspricebot && ./test_inventory_sync.sh
```

ثم افتح:

```text
/admin?token=admin2026
```

سترى حالة آخر مزامنة في قسم "حالة مزامنة المخزون".

## ملاحظة مهمة

لا ترفع ملف `.env` إلى GitHub. المفاتيح السرية تبقى فقط على السيرفر.
