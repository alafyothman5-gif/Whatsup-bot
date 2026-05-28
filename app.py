#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WhatsPriceBot V4.1 - Pharmacy Safe Vision

الفكرة:
- رسالة ترحيب منظمة باسم الصيدلية.
- يرد فقط على السعر والتوفر.
- لا يوجد حجز/طلب في هذه النسخة.
- أي سؤال تفاصيل/جرعة/حامل/أطفال/استعمال يتحول للأدمن.
- أي روشتة تتحول للأدمن دائمًا.
- صورة علبة دواء: يقرأها بالذكاء، ولو فيه شك بسيط تتحول للأدمن.
- صاحب الصيدلية يرد من لوحة الإدارة والرد يصل للزبون في واتساب.
"""

from flask import Flask, request, jsonify, redirect
import datetime
import json
import os
import re
import uuid
import requests
from difflib import SequenceMatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from vision import analyze_image_with_fallback

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "WhatsPrice2026")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "admin2026")
PHARMACY_NAME = os.getenv("PHARMACY_NAME", "الصيدلية")
ADMIN_PANEL_TITLE = os.getenv("ADMIN_PANEL_TITLE", "لوحة إدارة الصيدلية")

VISION_ENABLED = os.getenv("VISION_ENABLED", "true").lower() in ("1", "true", "yes", "on")

# مهم:
# 0.995 معناها لا يرد تلقائيًا إلا لو الثقة 99.5% أو أكثر.
# لو تريد أكثر صرامة خليها 0.999.
VISION_AUTO_REPLY_MIN_CONFIDENCE = float(os.getenv("VISION_AUTO_REPLY_MIN_CONFIDENCE", "0.995"))
VISION_AUTO_REPLY_MIN_MATCH_SCORE = float(os.getenv("VISION_AUTO_REPLY_MIN_MATCH_SCORE", "0.98"))
VISION_REQUIRE_EXACT_PRODUCT_MATCH = os.getenv("VISION_REQUIRE_EXACT_PRODUCT_MATCH", "true").lower() in ("1", "true", "yes", "on")

PRODUCTS_FILE = os.getenv("PRODUCTS_FILE", "products.json")
WEBHOOK_LOG = os.getenv("WEBHOOK_LOG", "webhook_log.txt")
SEND_LOG = os.getenv("SEND_LOG", "send_log.txt")
PENDING_FILE = os.getenv("PENDING_FILE", "pending_reviews.json")
ORDERS_FILE = os.getenv("ORDERS_FILE", "orders.json")
CONVERSATIONS_FILE = os.getenv("CONVERSATIONS_FILE", "conversations.json")
VISION_LOG = os.getenv("VISION_LOG", "vision_log.txt")
MEDIA_DIR = os.getenv("MEDIA_DIR", "media")

os.makedirs(MEDIA_DIR, exist_ok=True)


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def read_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def append_log(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def normalize_text(text):
    text = (text or "").lower().strip()

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
        "گ": "ق",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("سامسونق", "سامسونج")
    text = text.replace("سمسونج", "سامسونج")
    text = text.replace("ايفون", "iphone")
    text = text.replace("آيفون", "iphone")
    text = text.replace("ايربودز", "airpods")
    text = text.replace("اير بودز", "airpods")
    text = text.replace("برو ماكس", "pro max")
    text = text.replace("برو", "pro")
    text = text.replace("الترا", "ultra")

    stop_words = [
        "عندكم", "عندك", "في", "فيه", "متوفر", "متوفره", "متوفرة",
        "بكم", "كم", "سعر", "شن", "شنو", "لو", "موجود", "نبي", "ابي",
        "هذا", "هدا", "هاي", "هذه", "الصورة", "صورة"
    ]
    for w in stop_words:
        text = re.sub(rf"\b{re.escape(w)}\b", " ", text)

    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


DETAIL_KEYWORDS = [
    "جرعة", "جرعه", "كم مرة", "كم مره", "كم حبة", "كم حبه",
    "طريقة الاستخدام", "كيف نستعمل", "كيف ناخذ", "استعمال", "استخدام",
    "ينفع", "حامل", "حمل", "مرضع", "رضاعة", "طفل", "اطفال", "أطفال",
    "رضيع", "ضغط", "سكر", "حساسية", "حساسيه", "أعراض", "اعراض",
    "آثار", "اثار", "جانبية", "جانبيه", "موانع", "بديل", "بدائل",
    "تفاصيل", "تفصيل", "نبي تفاصيل", "ابي تفاصيل", "صيدلي",
    "نسأل", "اسأل", "استشارة", "استشاره", "روشتة", "وصفة", "وصفه",
    "دكتور", "طبيب", "مرض", "مريض",
    "حجز", "احجز", "طلب", "نطلب", "نبي نطلب", "نبي ناخد", "نبي نشتري"
]

PRESCRIPTION_KEYWORDS = [
    "روشتة", "روشته", "وصفة", "وصفه", "ورقة الدكتور", "الدكتور كاتب",
    "دكتور كاتب", "تحليل", "تقرير", "جرعات"
]


def has_detail_question(text):
    raw = (text or "").lower()
    clean = normalize_text(text)
    combined = f"{raw} {clean}"
    return any(k.lower() in combined for k in DETAIL_KEYWORDS)


def has_prescription_words(text):
    raw = (text or "").lower()
    clean = normalize_text(text)
    combined = f"{raw} {clean}"
    return any(k.lower() in combined for k in PRESCRIPTION_KEYWORDS)


def greeting():
    return f"أهلاً بك، شكرًا لتواصلك مع {PHARMACY_NAME} 🌿"


def ensure_products():
    if os.path.exists(PRODUCTS_FILE):
        return

    sample = [
        {
            "id": "panadol_500",
            "category": "مسكنات",
            "name": "Panadol 500mg",
            "price": "12 د.ل",
            "stock": "متوفر",
            "quantity": "20",
            "expiry_date": "2027-05",
            "notes": "للاستخدام والجرعة يرجى سؤال الصيدلي.",
            "aliases": ["panadol", "بندول", "بانادول", "paracetamol", "باراسيتامول"]
        },
        {
            "id": "augmentin_1g",
            "category": "مضادات حيوية",
            "name": "Augmentin 1g",
            "price": "35 د.ل",
            "stock": "متوفر",
            "quantity": "10",
            "expiry_date": "2026-12",
            "notes": "يصرف حسب إرشاد الطبيب أو الصيدلي.",
            "aliases": ["augmentin", "اوجمنتين", "اموكسكلاف", "amoxiclav"]
        },
        {
            "id": "iphone_15_pro",
            "category": "هواتف",
            "name": "iPhone 15 Pro",
            "price": "5200 د.ل",
            "stock": "متوفر",
            "quantity": "3",
            "expiry_date": "",
            "notes": "السعر قابل للتغيير حسب اللون والسعة",
            "aliases": ["iphone 15 pro", "15 pro", "ايفون 15 برو", "iphone برو", "ايفون برو"]
        },
        {
            "id": "s24_ultra",
            "category": "هواتف",
            "name": "Samsung S24 Ultra",
            "price": "5400 د.ل",
            "stock": "متوفر",
            "quantity": "2",
            "expiry_date": "",
            "notes": "متوفر حسب السعة واللون",
            "aliases": ["s24 ultra", "s24", "سامسونج s24", "سامسونق s24", "اس 24 الترا", "سامسونق الترا"]
        }
    ]
    write_json(PRODUCTS_FILE, sample)


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def load_products():
    ensure_products()
    return read_json(PRODUCTS_FILE, [])


def save_products(products):
    write_json(PRODUCTS_FILE, products)


def find_product(user_text):
    clean = normalize_text(user_text)
    products = load_products()

    if not clean:
        return None, 0.0, ""

    for product in products:
        candidates = [product.get("name", "")] + product.get("aliases", [])
        for candidate in candidates:
            c = normalize_text(candidate)
            if not c:
                continue
            if c == clean or c in clean or clean in c:
                return product, 1.0, candidate

    clean_words = set(clean.split())
    best = None
    best_score = 0.0
    best_alias = ""

    for product in products:
        candidates = [product.get("name", "")] + product.get("aliases", [])
        for candidate in candidates:
            c = normalize_text(candidate)
            c_words = set(c.split())
            if not c_words:
                continue
            overlap = len(clean_words & c_words) / max(len(c_words), 1)
            score = max(overlap, similarity(clean, c))
            if score > best_score:
                best = product
                best_score = score
                best_alias = candidate

    if best_score >= 0.75:
        return best, best_score, best_alias

    return None, best_score, best_alias


def strict_match_is_safe(vision_result, product, match_score):
    """
    لا نرد تلقائيًا على الصورة إلا لو:
    - Vision نجح.
    - المنتج موجود في قاعدة البيانات.
    - confidence من AI >= 99.5% افتراضيًا.
    - match_score >= 98%.
    - ولو VISION_REQUIRE_EXACT_PRODUCT_MATCH=true لازم الاسم المستخرج يطابق الاسم/alias بقوة.
    """
    if not vision_result.get("success"):
        return False, "vision_failed"

    if not product:
        return False, "product_not_found"

    image_type = str(vision_result.get("image_type", "")).lower()
    if image_type in ("prescription", "rx", "medical_prescription"):
        return False, "prescription_always_admin"

    try:
        confidence = float(vision_result.get("confidence") or 0)
    except Exception:
        confidence = 0.0

    if confidence > 1:
        confidence = confidence / 100.0

    if confidence < VISION_AUTO_REPLY_MIN_CONFIDENCE:
        return False, f"low_confidence_{confidence}"

    if match_score < VISION_AUTO_REPLY_MIN_MATCH_SCORE:
        return False, f"low_match_score_{match_score}"

    if VISION_REQUIRE_EXACT_PRODUCT_MATCH:
        guessed = normalize_text(vision_result.get("product_name", ""))
        possible = [normalize_text(product.get("name", ""))]
        possible += [normalize_text(a) for a in product.get("aliases", [])]

        exact_ok = False
        for p in possible:
            if p and (p == guessed or p in guessed or guessed in p):
                exact_ok = True
                break

        if not exact_ok:
            return False, "not_exact_enough"

    return True, "safe"


def product_reply(product):
    """Safe pharmacy reply: only availability and price, with greeting."""
    name = product.get("name", "المنتج")
    price = product.get("price", "غير محدد")
    stock = product.get("stock", "غير محدد")
    quantity = str(product.get("quantity", "") or "").strip()

    if "غير" in stock or quantity == "0":
        msg = (
            f"{greeting()}\n\n"
            "❌ المنتج غير متوفر حاليًا\n"
            f"المنتج: {name}"
        )
    else:
        msg = (
            f"{greeting()}\n\n"
            "✅ المنتج متوفر\n"
            f"المنتج: {name}\n"
            f"السعر: {price}"
        )

    return msg.strip()

def transfer_reply():
    return "✅ تم تحويل سؤالك للصيدلي.\nسيتم الرد عليك قريبًا."


def unknown_product_reply():
    return "✅ وصل طلبك.\nسيتم التأكد من توفر المنتج والرد عليك قريبًا."


def save_pending(kind, sender, name, text="", raw=None, media_id="", vision_result=None):
    pending = read_json(PENDING_FILE, [])
    item = {
        "id": str(uuid.uuid4())[:8],
        "created_at": now(),
        "kind": kind,
        "from": sender,
        "name": name,
        "text": text,
        "media_id": media_id,
        "status": "open",
        "vision_result": vision_result or {},
        "raw": raw or {}
    }
    pending.append(item)
    write_json(PENDING_FILE, pending)
    return item



def create_conversation_alert(sender, name, text, reason, product=None, raw=None, media_id=""):
    conversations = read_json(CONVERSATIONS_FILE, [])
    item = {
        "id": str(uuid.uuid4())[:8],
        "created_at": now(),
        "updated_at": now(),
        "from": sender,
        "name": name or "",
        "status": "open",
        "reason": reason,
        "last_product": product.get("name", "") if product else "",
        "last_product_id": product.get("id", "") if product else "",
        "media_id": media_id,
        "messages": [
            {"time": now(), "role": "customer", "text": text}
        ],
        "raw": raw or {}
    }
    conversations.append(item)
    write_json(CONVERSATIONS_FILE, conversations)
    return item


def close_conversation(conv_id):
    conversations = read_json(CONVERSATIONS_FILE, [])
    for conv in conversations:
        if conv.get("id") == conv_id:
            conv["status"] = "closed"
            conv["updated_at"] = now()
            write_json(CONVERSATIONS_FILE, conversations)
            return conv
    return None



def save_order(sender, name, text):
    orders = read_json(ORDERS_FILE, [])
    order = {
        "id": str(uuid.uuid4())[:8],
        "created_at": now(),
        "from": sender,
        "name": name,
        "text": text,
        "status": "new"
    }
    orders.append(order)
    write_json(ORDERS_FILE, orders)
    return order


def send_whatsapp_text(to, body):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        append_log(SEND_LOG, f"{now()} | NO_TOKEN_OR_PHONE_ID | to={to} | BODY={body}")
        return False, "NO_TOKEN_OR_PHONE_ID"

    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": body
        }
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        append_log(SEND_LOG, f"{now()} | STATUS={r.status_code} | BODY={body} | RESPONSE={r.text}")
        return r.status_code < 300, r.text
    except Exception as e:
        append_log(SEND_LOG, f"{now()} | EXCEPTION={e} | BODY={body}")
        return False, str(e)


def download_whatsapp_media(media_id):
    if not media_id or not WHATSAPP_TOKEN:
        return None, "", "NO_MEDIA_ID_OR_TOKEN"

    try:
        meta_url = f"https://graph.facebook.com/v25.0/{media_id}"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        r = requests.get(meta_url, headers=headers, timeout=20)
        if r.status_code >= 300:
            return None, "", f"META_MEDIA_INFO_ERROR {r.status_code}: {r.text}"

        info = r.json()
        media_url = info.get("url")
        mime_type = info.get("mime_type", "image/jpeg")

        if not media_url:
            return None, "", "NO_MEDIA_URL"

        media = requests.get(media_url, headers=headers, timeout=30)
        if media.status_code >= 300:
            return None, "", f"META_MEDIA_DOWNLOAD_ERROR {media.status_code}: {media.text}"

        return media.content, mime_type, ""

    except Exception as e:
        return None, "", f"MEDIA_EXCEPTION: {e}"


def extract_messages(data):
    out = []
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            contact_name = ""
            if contacts:
                contact_name = contacts[0].get("profile", {}).get("name", "")

            for msg in value.get("messages", []):
                msg_type = msg.get("type", "")
                text = ""
                media_id = ""

                if msg_type == "text":
                    text = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    media_id = msg.get("image", {}).get("id", "")
                    text = msg.get("image", {}).get("caption", "")

                out.append({
                    "from": msg.get("from", ""),
                    "name": contact_name,
                    "type": msg_type,
                    "text": text,
                    "media_id": media_id,
                    "raw": msg
                })
    return out


def handle_text(sender, name, text):
    product, score, alias = find_product(text)

    # Questions needing pharmacist/human details go to Admin Inbox.
    if has_detail_question(text):
        create_conversation_alert(
            sender=sender,
            name=name,
            text=text,
            reason="details_needed",
            product=product,
        )
        send_whatsapp_text(sender, transfer_reply())
        return

    # Known product: only availability + price.
    if product:
        send_whatsapp_text(sender, product_reply(product))
        return

    # Unknown product: convert to Admin Inbox.
    pending = save_pending("unknown_text", sender, name, text=text)
    create_conversation_alert(
        sender=sender,
        name=name,
        text=text,
        reason="unknown_product",
        product=None,
    )
    send_whatsapp_text(sender, unknown_product_reply())


def handle_image(sender, name, text, media_id, raw):
    # الروشتة أو أي صورة عليها وصفة/جرعات تتحول للأدمن مباشرة.
    if has_prescription_words(text):
        create_conversation_alert(sender, name, text or "روشتة/صورة تحتاج مراجعة", "prescription_caption", raw=raw, media_id=media_id)
        send_whatsapp_text(sender, prescription_reply())
        return

    if not VISION_ENABLED:
        pending = save_pending("image", sender, name, text=text, media_id=media_id, raw=raw)
        send_whatsapp_text(sender, f"وصلت الصورة ✅\nسيتم التحقق من المنتج والرد عليك بالسعر والتوفر.\nرقم المراجعة: {pending['id']}")
        return

    image_bytes, mime_type, media_error = download_whatsapp_media(media_id)

    if not image_bytes:
        vision_result = {"success": False, "error": media_error}
        append_log(VISION_LOG, f"{now()} | MEDIA_ERROR | {json.dumps(vision_result, ensure_ascii=False)}")
        pending = save_pending("image_media_download_failed", sender, name, text=text, media_id=media_id, raw=raw, vision_result=vision_result)
        send_whatsapp_text(sender, f"وصلت الصورة ✅\nلم أتمكن من قراءتها الآن وسيتم تحويلها للموظف.\nرقم المراجعة: {pending['id']}")
        return

    safe_media_id = re.sub(r"[^a-zA-Z0-9_-]", "_", media_id or str(uuid.uuid4())[:8])
    ext = ".jpg"
    if "png" in mime_type:
        ext = ".png"
    elif "webp" in mime_type:
        ext = ".webp"
    media_path = os.path.join(MEDIA_DIR, f"{safe_media_id}{ext}")
    try:
        with open(media_path, "wb") as f:
            f.write(image_bytes)
    except Exception:
        pass

    products = load_products()
    vision_result = analyze_image_with_fallback(
        image_bytes=image_bytes,
        mime_type=mime_type or "image/jpeg",
        caption=text or "",
        products=products
    )
    append_log(VISION_LOG, f"{now()} | RESULT | {json.dumps(vision_result, ensure_ascii=False)}")

    if str(vision_result.get("image_type", "")).lower() in ("prescription", "rx", "medical_prescription"):
        pending = save_pending("prescription_image", sender, name, text=text, media_id=media_id, raw=raw, vision_result=vision_result)
        create_conversation_alert(sender, name, text or "روشتة تحتاج مراجعة", "prescription_image", raw=raw, media_id=media_id)
        send_whatsapp_text(sender, prescription_reply())
        return

    guess_parts = []
    if text:
        guess_parts.append(text)
    for key in ("product_name", "brand", "visible_text", "generic_name"):
        value = vision_result.get(key)
        if value:
            guess_parts.append(str(value))

    guess_text = " ".join(guess_parts).strip()
    product, score, alias = find_product(guess_text)

    safe, reason = strict_match_is_safe(vision_result, product, score)

    if safe:
        reply = product_reply(product)
        reply += "\n\nتم التعرف على الصورة تلقائيًا ✅"
        send_whatsapp_text(sender, reply)
        return

    vision_result["strict_decision"] = "sent_to_admin"
    vision_result["strict_reason"] = reason
    vision_result["match_score"] = score
    vision_result["matched_product_id"] = product.get("id") if product else ""

    pending = save_pending("image_needs_review", sender, name, text=text, media_id=media_id, raw=raw, vision_result=vision_result)
    create_conversation_alert(sender, name, text or "صورة منتج", "image_needs_review", product=product, raw=raw, media_id=media_id)
    reply = (
        "✅ وصلت الصورة.\n"
        "سيتم التأكد من المنتج والرد عليك قريبًا."
    )
    send_whatsapp_text(sender, reply)


def esc(x):
    return str(x or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def admin_allowed():
    return request.args.get("token") == ADMIN_TOKEN


def admin_url(path="/admin"):
    return f"{path}?token={ADMIN_TOKEN}"


@app.get("/")
def home():
    return jsonify({
        "status": "running",
        "name": "WhatsPriceBot V4.1 Pharmacy Safe Vision",
        "pharmacy_name": PHARMACY_NAME,
        "time": now(),
        "meta_ready": bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID),
        "vision_enabled": VISION_ENABLED,
        "vision_auto_reply_min_confidence": VISION_AUTO_REPLY_MIN_CONFIDENCE,
        "vision_auto_reply_min_match_score": VISION_AUTO_REPLY_MIN_MATCH_SCORE
    })


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "products": len(load_products()),
        "pending": len(read_json(PENDING_FILE, [])),
        "orders": len(read_json(ORDERS_FILE, [])),
        "open_conversations": len([c for c in read_json(CONVERSATIONS_FILE, []) if c.get("status") == "open"]),
        "token_loaded": bool(WHATSAPP_TOKEN),
        "phone_number_id_loaded": bool(PHONE_NUMBER_ID),
        "vision_enabled": VISION_ENABLED
    })


@app.get("/admin")
def admin_dashboard():
    if not admin_allowed():
        return "Forbidden", 403

    products = load_products()
    pending = read_json(PENDING_FILE, [])
    orders = read_json(ORDERS_FILE, [])
    conversations = read_json(CONVERSATIONS_FILE, [])
    open_conversations = [c for c in conversations if c.get("status") == "open"]

    inbox_html = ""
    for c in sorted(open_conversations, key=lambda x: x.get("updated_at", ""), reverse=True):
        last_msg = c.get("messages", [{}])[-1].get("text", "")
        inbox_html += f"""
        <div class="ticket">
          <div class="ticket-head">
            <b>🔴 يحتاج رد</b>
            <span>{esc(c.get('updated_at'))}</span>
          </div>
          <p><b>الزبون:</b> {esc(c.get('from'))} — {esc(c.get('name'))}</p>
          <p><b>السبب:</b> {esc(c.get('reason'))}</p>
          <p><b>آخر منتج:</b> {esc(c.get('last_product'))}</p>
          <p class="msg">{esc(last_msg)}</p>

          <form method="post" action="/admin/reply?token={esc(ADMIN_TOKEN)}">
            <input type="hidden" name="conv_id" value="{esc(c.get('id'))}">
            <textarea name="reply" placeholder="اكتب رد الصيدلية هنا..." required></textarea>
            <button type="submit">إرسال للزبون</button>
          </form>

          <form method="post" action="/admin/close?token={esc(ADMIN_TOKEN)}">
            <input type="hidden" name="conv_id" value="{esc(c.get('id'))}">
            <button class="secondary" type="submit">إغلاق بدون رد</button>
          </form>
        </div>
        """

    if not inbox_html:
        inbox_html = "<p class='ok'>لا توجد طلبات تحتاج رد حاليًا ✅</p>"

    products_html = ""
    for p in products:
        aliases = ", ".join(p.get("aliases", []))
        products_html += f"""
        <tr>
          <td>{esc(p.get('id'))}</td>
          <td>{esc(p.get('category'))}</td>
          <td>{esc(p.get('name'))}</td>
          <td>{esc(p.get('price'))}</td>
          <td>{esc(p.get('stock'))}</td>
          <td>{esc(p.get('quantity'))}</td>
          <td><a class="small-btn" href="/admin/edit_product?token={esc(ADMIN_TOKEN)}&id={esc(p.get('id'))}">تعديل</a></td>
          <td>{esc(aliases)}</td>
        </tr>
        """

    orders_html = ""
    for o in orders[-30:]:
        orders_html += f"""
        <tr>
          <td>{esc(o.get('id'))}</td>
          <td>{esc(o.get('status'))}</td>
          <td>{esc(o.get('from'))}</td>
          <td>{esc(o.get('text'))}</td>
          <td>{esc(o.get('created_at'))}</td>
        </tr>
        """

    html = f"""
    <!doctype html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <meta http-equiv="refresh" content="15">
      <title>{esc(ADMIN_PANEL_TITLE)}</title>
      <style>
        body {{ font-family: Arial, sans-serif; background:#f4f6f8; padding:12px; color:#222; }}
        h1 {{ font-size:22px; margin:10px 0; }}
        .top {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap:10px; margin-bottom:12px; }}
        .stat {{ background:white; padding:14px; border-radius:14px; box-shadow:0 2px 8px #0001; }}
        .stat b {{ font-size:24px; color:#128c7e; display:block; }}
        .card {{ background:white; padding:14px; margin-bottom:14px; border-radius:14px; box-shadow:0 2px 8px #0001; overflow:auto; }}
        table {{ width:100%; border-collapse:collapse; font-size:14px; min-width:760px; }}
        th, td {{ border-bottom:1px solid #ddd; padding:8px; text-align:right; vertical-align:top; }}
        th {{ background:#eee; }}
        input, textarea {{ width:100%; box-sizing:border-box; padding:10px; margin:5px 0; border:1px solid #ccc; border-radius:10px; font-size:15px; }}
        textarea {{ min-height:80px; }}
        button, .small-btn {{ padding:9px 13px; margin:4px 0; border:0; border-radius:10px; cursor:pointer; background:#128c7e; color:white; text-decoration:none; display:inline-block; }}
        .secondary {{ background:#777; }}
        .danger {{ background:#c0392b; }}
        .ok {{ color:green; font-weight:bold; }}
        .ticket {{ border:1px solid #eee; border-radius:14px; padding:12px; margin-bottom:12px; background:#fffdfd; }}
        .ticket-head {{ display:flex; justify-content:space-between; gap:10px; color:#c0392b; }}
        .msg {{ background:#f7f7f7; padding:10px; border-radius:10px; white-space:pre-wrap; }}
        .nav a {{ display:inline-block; margin:3px; padding:8px 10px; background:#e9f6f4; color:#128c7e; border-radius:10px; text-decoration:none; }}
        @media(max-width:700px) {{
          body {{ padding:8px; }}
          .card {{ padding:10px; }}
          h1 {{ font-size:20px; }}
        }}
      </style>
    </head>
    <body>
      <h1>لوحة إدارة WhatsPriceBot</h1>
      <div class="nav">
        <a href="#inbox">🔔 الطلبات</a>
        <a href="#products">💊 المنتجات</a>
        <a href="#add">➕ إضافة دواء</a>
        
      </div>

      <div class="top">
        <div class="stat">طلبات تحتاج رد <b>{len(open_conversations)}</b></div>
        <div class="stat">المنتجات <b>{len(products)}</b></div>
        <div class="stat">الطلبات <b>{len(orders)}</b></div>
        <div class="stat">مراجعات <b>{len(pending)}</b></div>
      </div>

      <div id="inbox" class="card">
        <h2>🔔 إشعارات تحتاج رد</h2>
        {inbox_html}
      </div>

      <div id="add" class="card">
        <h2>➕ إضافة دواء / منتج</h2>
        <form method="post" action="/admin/add_product?token={esc(ADMIN_TOKEN)}">
          <input name="id" placeholder="id مثل panadol_500" required>
          <input name="category" placeholder="القسم">
          <input name="name" placeholder="اسم المنتج" required>
          <input name="price" placeholder="السعر" required>
          <input name="stock" placeholder="متوفر أو غير متوفر" value="متوفر">
          <input name="quantity" placeholder="الكمية">
          <input name="aliases" placeholder="أسماء بديلة مفصولة بفواصل: بندول, بانادول, panadol">
          <button type="submit">حفظ المنتج</button>
        </form>
      </div>

      <div id="products" class="card">
        <h2>💊 المنتجات</h2>
        <table>
          <tr><th>ID</th><th>القسم</th><th>الاسم</th><th>السعر</th><th>التوفر</th><th>الكمية</th><th>تعديل</th><th>الأسماء البديلة</th></tr>
          {products_html}
        </table>
      </div>
    </body>
    </html>
    """
    return html


@app.post("/admin/reply")
def admin_reply():
    if not admin_allowed():
        return "Forbidden", 403

    conv_id = request.form.get("conv_id", "").strip()
    reply = request.form.get("reply", "").strip()
    conversations = read_json(CONVERSATIONS_FILE, [])
    conv = next((c for c in conversations if c.get("id") == conv_id), None)
    if not conv:
        return "Conversation not found", 404
    if not reply:
        return "Reply is empty", 400

    ok, resp = send_whatsapp_text(conv.get("from"), reply)
    conv.setdefault("messages", []).append({"time": now(), "role": "admin", "text": reply})
    conv["updated_at"] = now()
    conv["status"] = "closed" if ok else "send_failed"
    conv["last_send_result"] = str(resp)[:1000]
    write_json(CONVERSATIONS_FILE, conversations)
    return redirect(admin_url())


@app.post("/admin/close")
def admin_close():
    if not admin_allowed():
        return "Forbidden", 403
    conv_id = request.form.get("conv_id", "").strip()
    close_conversation(conv_id)
    return redirect(admin_url())


@app.get("/admin/edit_product")
def admin_edit_product():
    if not admin_allowed():
        return "Forbidden", 403
    product_id = request.args.get("id", "")
    products = load_products()
    product = next((p for p in products if p.get("id") == product_id), None)
    if not product:
        return "Product not found", 404
    aliases = ", ".join(product.get("aliases", []))
    html = f"""
    <!doctype html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>تعديل منتج</title>
      <style>
        body {{ font-family: Arial; background:#f4f6f8; padding:14px; }}
        .card {{ background:white; padding:16px; border-radius:14px; max-width:700px; margin:auto; box-shadow:0 2px 8px #0001; }}
        input, textarea {{ width:100%; box-sizing:border-box; padding:10px; margin:6px 0; border:1px solid #ccc; border-radius:10px; }}
        button, a {{ padding:10px 13px; margin:5px 0; border:0; border-radius:10px; background:#128c7e; color:white; text-decoration:none; display:inline-block; }}
        .danger {{ background:#c0392b; }}
      </style>
    </head>
    <body>
    <div class="card">
      <h2>تعديل المنتج</h2>
      <form method="post" action="/admin/update_product?token={esc(ADMIN_TOKEN)}">
        <input type="hidden" name="id" value="{esc(product.get('id'))}">
        <label>الاسم</label>
        <input name="name" value="{esc(product.get('name'))}" required>
        <label>السعر</label>
        <input name="price" value="{esc(product.get('price'))}" required>
        <label>التوفر</label>
        <input name="stock" value="{esc(product.get('stock'))}">
        <label>الكمية</label>
        <input name="quantity" value="{esc(product.get('quantity'))}">
        <label>القسم</label>
        <input name="category" value="{esc(product.get('category'))}">
        <label>أسماء بديلة</label>
        <textarea name="aliases">{esc(aliases)}</textarea>
        <button type="submit">حفظ</button>
        <a href="{admin_url()}">رجوع</a>
      </form>

      <form method="post" action="/admin/quick_stock?token={esc(ADMIN_TOKEN)}">
        <input type="hidden" name="id" value="{esc(product.get('id'))}">
        <button name="stock" value="متوفر">✅ متوفر</button>
        <button class="danger" name="stock" value="غير متوفر">❌ غير متوفر</button>
      </form>
    </div>
    </body>
    </html>
    """
    return html


@app.post("/admin/update_product")
def admin_update_product():
    if not admin_allowed():
        return "Forbidden", 403
    product_id = request.form.get("id", "").strip()
    products = load_products()
    for p in products:
        if p.get("id") == product_id:
            p["name"] = request.form.get("name", "").strip()
            p["price"] = request.form.get("price", "").strip()
            p["stock"] = request.form.get("stock", "متوفر").strip()
            p["quantity"] = request.form.get("quantity", "").strip()
            p["category"] = request.form.get("category", "").strip()
            p["aliases"] = [x.strip() for x in request.form.get("aliases", "").split(",") if x.strip()]
            save_products(products)
            return redirect(admin_url())
    return "Product not found", 404


@app.post("/admin/quick_stock")
def admin_quick_stock():
    if not admin_allowed():
        return "Forbidden", 403
    product_id = request.form.get("id", "").strip()
    stock = request.form.get("stock", "").strip()
    products = load_products()
    for p in products:
        if p.get("id") == product_id:
            p["stock"] = stock
            if "غير" in stock:
                p["quantity"] = "0"
            save_products(products)
            return redirect(admin_url())
    return "Product not found", 404

@app.post("/admin/add_product")
def admin_add_product():
    if not admin_allowed():
        return "Forbidden", 403

    products = load_products()
    product_id = request.form.get("id", "").strip()
    if not product_id:
        return "Missing id", 400

    aliases = [x.strip() for x in request.form.get("aliases", "").split(",") if x.strip()]
    item = {
        "id": product_id,
        "category": request.form.get("category", "").strip(),
        "name": request.form.get("name", "").strip(),
        "price": request.form.get("price", "").strip(),
        "stock": request.form.get("stock", "متوفر").strip(),
        "quantity": request.form.get("quantity", "").strip(),
        "expiry_date": request.form.get("expiry_date", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "aliases": aliases,
    }

    replaced = False
    for i, p in enumerate(products):
        if p.get("id") == product_id:
            old_aliases = p.get("aliases", [])
            for a in old_aliases:
                if a not in item["aliases"]:
                    item["aliases"].append(a)
            products[i] = item
            replaced = True
            break
    if not replaced:
        products.append(item)

    save_products(products)
    return redirect(admin_url())


@app.post("/admin/add_alias")
def admin_add_alias():
    if not admin_allowed():
        return "Forbidden", 403

    product_id = request.form.get("product_id", "").strip()
    alias = request.form.get("alias", "").strip()

    products = load_products()
    for p in products:
        if p.get("id") == product_id:
            aliases = p.setdefault("aliases", [])
            if alias and alias not in aliases:
                aliases.append(alias)
            save_products(products)
            return redirect(admin_url())

    return f"Product not found: {esc(product_id)}", 404


@app.post("/admin/resolve")
def admin_resolve():
    if not admin_allowed():
        return "Forbidden", 403

    pending_id = request.form.get("pending_id", "").strip()
    product_id = request.form.get("product_id", "").strip()
    alias = request.form.get("alias", "").strip()

    pending = read_json(PENDING_FILE, [])
    products = load_products()

    item = next((x for x in pending if x.get("id") == pending_id), None)
    product = next((x for x in products if x.get("id") == product_id), None)

    if not item:
        return f"Pending not found: {esc(pending_id)}", 404
    if not product:
        return f"Product not found: {esc(product_id)}", 404

    if not alias:
        alias = item.get("text", "").strip()
        if not alias:
            vr = item.get("vision_result") or {}
            alias = vr.get("product_name", "")

    if alias:
        aliases = product.setdefault("aliases", [])
        if alias not in aliases:
            aliases.append(alias)

    item["status"] = "resolved"
    item["resolved_at"] = now()
    item["resolved_product_id"] = product_id
    item["resolved_alias"] = alias

    write_json(PENDING_FILE, pending)
    save_products(products)

    if item.get("from"):
        send_whatsapp_text(item["from"], product_reply(product))

    return redirect(admin_url())


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification failed", 403


@app.post("/webhook")
def receive_message():
    data = request.get_json(silent=True) or {}

    append_log(WEBHOOK_LOG, "\n--- NEW WEBHOOK ---")
    append_log(WEBHOOK_LOG, now())
    append_log(WEBHOOK_LOG, json.dumps(data, ensure_ascii=False, indent=2))

    messages = extract_messages(data)

    for msg in messages:
        sender = msg["from"]
        name = msg["name"]
        msg_type = msg["type"]

        if msg_type == "text":
            handle_text(sender, name, msg["text"])
        elif msg_type == "image":
            handle_image(sender, name, msg["text"], msg["media_id"], msg["raw"])
        else:
            pending = save_pending("unsupported", sender, name, raw=msg["raw"])
            send_whatsapp_text(
                sender,
                f"وصلت رسالتك ✅\nحاليًا أقدر أتعامل مع النصوص والصور فقط.\nرقم المراجعة: {pending['id']}"
            )

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    ensure_products()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8090")))
