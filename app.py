from flask import Flask, request, jsonify
import datetime
import json
import os
import re
import uuid
import requests
from difflib import SequenceMatcher

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "WhatsPrice2026")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "1048608088345554")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")

PRODUCTS_FILE = "products.json"
WEBHOOK_LOG = "webhook_log.txt"
SEND_LOG = "send_log.txt"
PENDING_FILE = "pending_reviews.json"
ORDERS_FILE = "orders.json"
MEDIA_DIR = "media"

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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    text = text.replace("ايفون", "iphone")
    text = text.replace("آيفون", "iphone")
    text = text.replace("ايربودز", "airpods")
    text = text.replace("برو ماكس", "pro max")
    text = text.replace("برو", "pro")
    text = text.replace("الترا", "ultra")

    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def ensure_products():
    if os.path.exists(PRODUCTS_FILE):
        return

    sample = [
        {
            "id": "iphone_15_pro",
            "name": "iPhone 15 Pro",
            "price": "5200 د.ل",
            "stock": "متوفر",
            "notes": "السعر قابل للتغيير حسب اللون والسعة",
            "aliases": ["iphone 15 pro", "15 pro", "ايفون 15 برو", "iphone برو", "ايفون برو"]
        },
        {
            "id": "s24_ultra",
            "name": "Samsung S24 Ultra",
            "price": "5400 د.ل",
            "stock": "متوفر",
            "notes": "متوفر حسب السعة واللون",
            "aliases": ["s24 ultra", "s24", "سامسونج s24", "سامسونق s24", "اس 24 الترا", "سامسونق الترا"]
        },
        {
            "id": "airpods_pro",
            "name": "AirPods Pro",
            "price": "850 د.ل",
            "stock": "غير متوفر",
            "notes": "يمكن توفيره بالطلب",
            "aliases": ["airpods pro", "airpods", "ايربودز", "ايربودز برو"]
        }
    ]
    write_json(PRODUCTS_FILE, sample)


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def load_products():
    ensure_products()
    return read_json(PRODUCTS_FILE, [])


def find_product(user_text):
    clean = normalize_text(user_text)
    products = load_products()

    # 1) exact / contains match first
    for product in products:
        candidates = [product.get("name", "")] + product.get("aliases", [])
        for candidate in candidates:
            c = normalize_text(candidate)
            if not c:
                continue

            if c == clean or c in clean or clean in c:
                return product, 1.0, candidate

    # 2) word overlap match
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

    # لا نقبل تشابه ضعيف حتى لا يرجع منتج غلط
    if best_score >= 0.75:
        return best, best_score, best_alias

    return None, best_score, best_alias


def product_reply(product):
    name = product.get("name", "المنتج")
    price = product.get("price", "غير محدد")
    stock = product.get("stock", "غير محدد")
    notes = product.get("notes", "")

    if "غير" in stock:
        msg = (
            f"المنتج: {name}\n"
            f"السعر: {price}\n"
            f"الحالة: {stock} ❌"
        )
    else:
        msg = (
            f"نعم متوفر ✅\n"
            f"المنتج: {name}\n"
            f"السعر: {price}\n"
            f"الحالة: {stock}"
        )

    if notes:
        msg += f"\nملاحظة: {notes}"

    msg += "\n\nلو تبي نجهز لك الطلب، اكتب: نبي نطلب"
    return msg


def save_pending(kind, sender, name, text="", raw=None, media_id=""):
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
        "raw": raw or {}
    }
    pending.append(item)
    write_json(PENDING_FILE, pending)
    return item


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
    if not WHATSAPP_TOKEN:
        append_log(SEND_LOG, f"{now()} | NO_TOKEN | to={to} | body={body}")
        return False, "NO_TOKEN"

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
        append_log(SEND_LOG, f"{now()} | EXCEPTION={e}")
        return False, str(e)


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
    clean = normalize_text(text)

    order_words = ["نبي نطلب", "نبي طلب", "نطلب", "نبيه", "ناخده", "نبي ناخد", "احجز", "اطلب"]
    if any(w in clean for w in order_words):
        order = save_order(sender, name, text)
        reply = (
            f"تم تسجيل طلبك ✅\n"
            f"رقم الطلب: {order['id']}\n"
            f"سيتم التواصل معك من الموظف للتأكيد."
        )
        send_whatsapp_text(sender, reply)
        return

    product, score, alias = find_product(text)

    if product:
        reply = product_reply(product)
        send_whatsapp_text(sender, reply)
        return

    pending = save_pending("unknown_text", sender, name, text=text)
    reply = (
        "وصلت رسالتك ✅\n"
        "لم أتعرف على المنتج بدقة.\n"
        "سيتم تحويلها للموظف للمراجعة.\n"
        f"رقم المراجعة: {pending['id']}"
    )
    send_whatsapp_text(sender, reply)


def handle_image(sender, name, text, media_id, raw):
    pending = save_pending("image", sender, name, text=text, media_id=media_id, raw=raw)
    reply = (
        "وصلت الصورة ✅\n"
        "سيتم التحقق من المنتج والرد عليك بالسعر والتوفر.\n"
        f"رقم المراجعة: {pending['id']}"
    )
    send_whatsapp_text(sender, reply)


@app.get("/")
def home():
    return jsonify({
        "status": "running",
        "name": "WhatsPriceBot V2",
        "time": now()
    })


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "products": len(load_products()),
        "pending": len(read_json(PENDING_FILE, [])),
        "orders": len(read_json(ORDERS_FILE, [])),
        "token_loaded": bool(WHATSAPP_TOKEN)
    })


@app.get("/admin/products")
def admin_products():
    return jsonify(load_products())


@app.get("/admin/pending")
def admin_pending():
    return jsonify(read_json(PENDING_FILE, []))


@app.get("/admin/orders")
def admin_orders():
    return jsonify(read_json(ORDERS_FILE, []))


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
    app.run(host="0.0.0.0", port=8090)
