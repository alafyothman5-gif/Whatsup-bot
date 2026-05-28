#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsPriceBot V4.3 Inventory Sync Safe
- Stable admin panel, no auto-refresh flicker.
- Pharmacy safe replies: only availability + prices.
- Strip/box prices, strip count, quantity, and expiry fields.
- Human takeover/admin inbox.
- Product image recognition with strict safety.
- Prescriptions and any medical/detail question go to admin.
- Safe inventory sync API for external scanner/agent with token, validation, and backups.
"""

from __future__ import annotations

import datetime as _dt
import hmac
import json
import os
import re
import shutil
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, redirect, render_template_string, request, send_from_directory, url_for

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from vision import analyze_image_with_fallback
except Exception:
    analyze_image_with_fallback = None

try:
    from text_ai import resolve_product_from_text_ai
except Exception:
    resolve_product_from_text_ai = None

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "WhatsPrice2026")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "admin2026")
INVENTORY_SYNC_TOKEN = os.getenv("INVENTORY_SYNC_TOKEN", "").strip()
MAX_SYNC_PRODUCTS = int(os.getenv("MAX_SYNC_PRODUCTS", "50000"))
ALLOW_EMPTY_INVENTORY_SYNC = os.getenv("ALLOW_EMPTY_INVENTORY_SYNC", "false").lower() in {"1", "true", "yes", "on"}

PHARMACY_NAME = os.getenv("PHARMACY_NAME", "صيدلية بدر البشرية")
ADMIN_PANEL_TITLE = os.getenv("ADMIN_PANEL_TITLE", f"لوحة إدارة {PHARMACY_NAME}")
PORT = int(os.getenv("PORT", "8090"))

VISION_ENABLED = os.getenv("VISION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
VISION_AUTO_REPLY_MIN_CONFIDENCE = float(os.getenv("VISION_AUTO_REPLY_MIN_CONFIDENCE", "0.995"))
VISION_AUTO_REPLY_MIN_MATCH_SCORE = float(os.getenv("VISION_AUTO_REPLY_MIN_MATCH_SCORE", "0.98"))
VISION_REQUIRE_EXACT_PRODUCT_MATCH = os.getenv("VISION_REQUIRE_EXACT_PRODUCT_MATCH", "true").lower() in {"1", "true", "yes", "on"}
TEXT_AI_ENABLED = os.getenv("TEXT_AI_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
TEXT_AI_MIN_CONFIDENCE = float(os.getenv("TEXT_AI_MIN_CONFIDENCE", "0.90"))

ROOT = Path(__file__).resolve().parent
PRODUCTS_FILE = ROOT / os.getenv("PRODUCTS_FILE", "products.json")
PENDING_FILE = ROOT / os.getenv("PENDING_FILE", "pending_reviews.json")
CONVERSATIONS_FILE = ROOT / os.getenv("CONVERSATIONS_FILE", "conversations.json")
USER_STATE_FILE = ROOT / os.getenv("USER_STATE_FILE", "user_state.json")
WEBHOOK_LOG = ROOT / os.getenv("WEBHOOK_LOG", "webhook_log.txt")
SEND_LOG = ROOT / os.getenv("SEND_LOG", "send_log.txt")
VISION_LOG = ROOT / os.getenv("VISION_LOG", "vision_log.txt")
TEXT_AI_LOG = ROOT / os.getenv("TEXT_AI_LOG", "text_ai.log")
SYNC_LOG = ROOT / os.getenv("SYNC_LOG", "inventory_sync.log")
SYNC_STATUS_FILE = ROOT / os.getenv("SYNC_STATUS_FILE", "inventory_sync_status.json")
BACKUP_DIR = ROOT / os.getenv("BACKUP_DIR", "backups")
MEDIA_DIR = ROOT / os.getenv("MEDIA_DIR", "media")
MEDIA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

DETAIL_KEYWORDS = [
    "جرعة", "جرعه", "كم مرة", "كم مره", "كم حبة", "كم حبه", "طريقة الاستخدام",
    "كيف نستعمل", "كيف ناخذ", "استعمال", "استخدام", "ينفع", "ينفعني",
    "حامل", "حمل", "مرضع", "رضاعة", "رضاعه", "طفل", "اطفال", "أطفال", "رضيع",
    "ضغط", "سكر", "حساسية", "حساسيه", "أعراض", "اعراض", "آثار", "اثار",
    "جانبية", "جانبيه", "موانع", "بديل", "بدائل", "تفاصيل", "تفصيل",
    "نبي تفاصيل", "ابي تفاصيل", "صيدلي", "نسأل", "اسأل", "استشارة", "استشاره",
    "روشتة", "روشته", "وصفة", "وصفه", "دكتور", "طبيب", "مرض", "مريض",
]

PRESCRIPTION_WORDS = [
    "روشتة", "روشته", "وصفة", "وصفه", "ورقة الدكتور", "الدكتور كاتب", "دكتور كاتب",
    "تحليل", "تقرير", "جرعة", "جرعات", "prescription", "rx",
]

STOP_WORDS = [
    "عندكم", "عندك", "في", "فيه", "متوفر", "متوفره", "متوفرة", "بكم", "كم",
    "سعر", "شن", "شنو", "لو", "موجود", "نبي", "ابي", "هذا", "هدا", "هاي", "هذه",
    "الصورة", "صورة", "هل", "ممكن", "دواء", "علاج",
]


def now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_log(path: Path, text: str) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def greeting() -> str:
    return f"أهلاً بك، شكرًا لتواصلك مع {PHARMACY_NAME} 🌿"


def normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    for old, new in {"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "گ": "ق"}.items():
        text = text.replace(old, new)
    replacements = {
        "سامسونق": "سامسونج",
        "سمسونج": "سامسونج",
        "ايفون": "iphone",
        "آيفون": "iphone",
        "ايربودز": "airpods",
        "اير بودز": "airpods",
        "برو ماكس": "pro max",
        "برو": "pro",
        "الترا": "ultra",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    for word in STOP_WORDS:
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def contains_any(text: str, words: List[str]) -> bool:
    raw = (text or "").lower()
    norm = normalize_text(text)
    combined = f"{raw} {norm}"
    return any(w.lower() in combined for w in words)


def has_detail_question(text: str) -> bool:
    return contains_any(text, DETAIL_KEYWORDS)


def has_prescription_words(text: str) -> bool:
    return contains_any(text, PRESCRIPTION_WORDS)


def ensure_products() -> None:
    if PRODUCTS_FILE.exists():
        return
    sample = [
        {
            "id": "panadol_500",
            "category": "مسكنات",
            "name": "Panadol 500mg",
            "price": "الشريط: 8 د.ل | العلبة: 16 د.ل",
            "price_strip": "8 د.ل",
            "price_box": "16 د.ل",
            "strips_count": "12",
            "stock": "متوفر",
            "quantity": "20",
            "expiry_date": "2027-05",
            "notes": "",
            "aliases": ["panadol", "بندول", "بانادول", "paracetamol", "باراسيتامول"],
        },
        {
            "id": "augmentin_1g",
            "category": "مضادات حيوية",
            "name": "Augmentin 1g",
            "price": "35 د.ل",
            "price_strip": "",
            "price_box": "35 د.ل",
            "strips_count": "",
            "stock": "متوفر",
            "quantity": "10",
            "expiry_date": "2026-12",
            "notes": "",
            "aliases": ["augmentin", "اوجمنتين", "اموكسكلاف", "amoxiclav"],
        },
        {
            "id": "brufen_400",
            "category": "مسكنات",
            "name": "Brufen 400mg",
            "price": "18 د.ل",
            "price_strip": "",
            "price_box": "18 د.ل",
            "strips_count": "",
            "stock": "غير متوفر",
            "quantity": "0",
            "expiry_date": "",
            "notes": "",
            "aliases": ["brufen", "بروفين", "بروفن", "ibuprofen", "ايبوبروفين"],
        },
    ]
    write_json(PRODUCTS_FILE, sample)


def load_products() -> List[Dict[str, Any]]:
    ensure_products()
    data = read_json(PRODUCTS_FILE, [])
    return data if isinstance(data, list) else []


def save_products(products: List[Dict[str, Any]]) -> None:
    write_json(PRODUCTS_FILE, products)


def get_sync_status() -> Dict[str, Any]:
    status = read_json(SYNC_STATUS_FILE, {})
    return status if isinstance(status, dict) else {}


def save_sync_status(status: Dict[str, Any]) -> None:
    write_json(SYNC_STATUS_FILE, status)


def sync_auth_token_from_request() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return (request.headers.get("X-Inventory-Token", "") or request.args.get("sync_token", "") or request.args.get("token", "")).strip()


def sync_auth_ok() -> bool:
    if not INVENTORY_SYNC_TOKEN:
        return False
    supplied = sync_auth_token_from_request()
    return bool(supplied) and hmac.compare_digest(supplied, INVENTORY_SYNC_TOKEN)


def first_value(data: Dict[str, Any], keys: List[str], default: str = "") -> str:
    for key in keys:
        if key in data and data.get(key) is not None:
            return str(data.get(key)).strip()
    return default


def parse_aliases(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = []
        for item in value:
            if item is None:
                continue
            raw.extend(str(item).replace("؛", ",").split(","))
    else:
        raw = str(value).replace("؛", ",").replace("|", ",").split(",")
    aliases = []
    for item in raw:
        item = item.strip()
        if item and item not in aliases:
            aliases.append(item)
    return aliases[:20]


def parse_number_like(value: Any) -> Optional[float]:
    if value is None:
        return None
    txt = str(value).strip()
    if not txt:
        return None
    txt = txt.replace("٫", ".").replace(",", ".")
    txt = re.sub(r"[^0-9.\-]", "", txt)
    if not txt or txt in {".", "-"}:
        return None
    try:
        return float(txt)
    except Exception:
        return None


def stable_product_id(name: str, barcode: str = "", product_id: str = "") -> str:
    raw = product_id or barcode or name or str(uuid.uuid4())[:8]
    raw = normalize_text(str(raw))
    raw = re.sub(r"[^a-zA-Z0-9_\u0600-\u06FF]+", "_", raw).strip("_")
    if not raw:
        raw = str(uuid.uuid4())[:8]
    return raw[:80]


def infer_stock(stock_text: str, quantity_text: str) -> str:
    txt = normalize_text(stock_text)
    qty = parse_number_like(quantity_text)
    if txt:
        if any(w in txt for w in ["غير", "ناقص", "نفد", "out", "no", "false"]):
            return "غير متوفر"
        if any(w in txt for w in ["متوفر", "available", "yes", "true", "in stock"]):
            return "متوفر"
    if qty is not None:
        return "متوفر" if qty > 0 else "غير متوفر"
    return stock_text.strip() or "متوفر"


def normalize_inventory_product(raw: Dict[str, Any], idx: int) -> Tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(raw, dict):
        return None, "item_not_object"
    name = first_value(raw, [
        "name", "product_name", "item_name", "drug_name", "medicine_name", "title",
        "اسم المنتج", "الاسم", "اسم الصنف", "الصنف", "الدواء", "اسم الدواء"
    ])
    if not name:
        return None, "missing_name"
    barcode = first_value(raw, ["barcode", "bar_code", "code", "sku", "باركود", "الباركود", "كود", "كود الصنف"])
    product_id = first_value(raw, ["id", "product_id", "item_id", "drug_id", "معرف", "رقم الصنف"])
    category = first_value(raw, ["category", "group", "department", "classification", "القسم", "التصنيف", "المجموعة"])
    price_strip = first_value(raw, ["price_strip", "strip_price", "price_per_strip", "سعر الشريط", "سعر_الشريط"])
    price_box = first_value(raw, ["price_box", "box_price", "sale_price", "retail_price", "price", "سعر العلبة", "سعر_العلبة", "سعر البيع", "السعر"])
    price = first_value(raw, ["display_price", "price_text", "price", "السعر العام", "السعر"])
    strips_count = first_value(raw, ["strips_count", "strips_per_box", "عدد الشرائط", "عدد_الشرائط"])
    quantity = first_value(raw, ["quantity", "qty", "stock_qty", "balance", "available_qty", "الكمية", "الرصيد", "المخزون"])
    stock_raw = first_value(raw, ["stock", "availability", "status", "الحالة", "التوفر"])
    expiry_date = first_value(raw, ["expiry_date", "expiry", "exp_date", "expire_date", "expiration_date", "الصلاحية", "تاريخ الصلاحية"])
    manufacturer = first_value(raw, ["manufacturer", "company", "brand", "الشركة", "الشركة المصنعة", "العلامة"])
    notes = first_value(raw, ["notes", "note", "ملاحظات", "ملاحظة"])
    aliases = parse_aliases(raw.get("aliases") or raw.get("alias") or raw.get("أسماء بديلة") or raw.get("اسماء بديلة"))
    for extra in [barcode, manufacturer]:
        if extra and extra not in aliases:
            aliases.append(extra)
    # Add the name as an alias candidate for easier matching, without duplicates.
    if name not in aliases:
        aliases.insert(0, name)
    stock = infer_stock(stock_raw, quantity)
    price = make_price_from_fields(price, price_strip, price_box)
    item = {
        "id": stable_product_id(name, barcode, product_id),
        "category": category,
        "name": name,
        "barcode": barcode,
        "manufacturer": manufacturer,
        "price": price,
        "price_strip": price_strip,
        "price_box": price_box,
        "strips_count": strips_count,
        "stock": stock,
        "quantity": quantity,
        "expiry_date": expiry_date,
        "notes": notes,
        "aliases": aliases,
    }
    return item, "ok"


def normalize_inventory_payload(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if isinstance(payload, list):
        raw_products = payload
        meta = {"source": "raw_list"}
    elif isinstance(payload, dict):
        raw_products = payload.get("products") or payload.get("items") or payload.get("inventory") or []
        meta = {
            "source": str(payload.get("source") or "unknown"),
            "client_id": str(payload.get("client_id") or payload.get("store_id") or ""),
            "mode": str(payload.get("mode") or "replace"),
        }
    else:
        raise ValueError("Payload must be a JSON list or object containing products")
    if not isinstance(raw_products, list):
        raise ValueError("products must be a list")
    if len(raw_products) > MAX_SYNC_PRODUCTS:
        raise ValueError(f"Too many products: {len(raw_products)} > {MAX_SYNC_PRODUCTS}")
    products: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen_ids = set()
    for idx, raw in enumerate(raw_products, start=1):
        item, reason = normalize_inventory_product(raw, idx)
        if not item:
            if len(skipped) < 30:
                skipped.append({"index": idx, "reason": reason})
            continue
        base_id = item["id"]
        if base_id in seen_ids:
            suffix = 2
            new_id = f"{base_id}_{suffix}"
            while new_id in seen_ids:
                suffix += 1
                new_id = f"{base_id}_{suffix}"
            item["id"] = new_id
        seen_ids.add(item["id"])
        products.append(item)
    details = {
        **meta,
        "received_count": len(raw_products),
        "valid_count": len(products),
        "skipped_count": len(raw_products) - len(products),
        "skipped_examples": skipped,
    }
    return products, details


def backup_products_file(reason: str = "inventory_sync") -> str:
    if not PRODUCTS_FILE.exists():
        return ""
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"products_{reason}_{stamp}.json"
    backup_path = BACKUP_DIR / backup_name
    shutil.copy2(PRODUCTS_FILE, backup_path)
    return str(backup_path.relative_to(ROOT))


def apply_inventory_sync(payload: Any) -> Tuple[bool, Dict[str, Any]]:
    try:
        products, details = normalize_inventory_payload(payload)
        if not products and not ALLOW_EMPTY_INVENTORY_SYNC:
            raise ValueError("No valid products found. Empty sync is blocked for safety.")
        backup_file = backup_products_file()
        save_products(products)
        status = {
            "ok": True,
            "last_sync_at": now(),
            "products_count": len(products),
            "backup_file": backup_file,
            "last_error": "",
            **details,
        }
        save_sync_status(status)
        append_log(SYNC_LOG, f"{now()} | OK | {json.dumps(status, ensure_ascii=False)}")
        return True, status
    except Exception as e:
        status = get_sync_status()
        status.update({"ok": False, "last_error": str(e), "last_failed_at": now()})
        save_sync_status(status)
        append_log(SYNC_LOG, f"{now()} | ERROR | {e}")
        return False, status


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_product(user_text: str) -> Tuple[Optional[Dict[str, Any]], float, str]:
    clean = normalize_text(user_text)
    if not clean:
        return None, 0.0, ""
    products = load_products()

    for product in products:
        candidates = [product.get("name", "")] + list(product.get("aliases", []) or [])
        for candidate in candidates:
            c = normalize_text(str(candidate))
            if not c:
                continue
            if c == clean or c in clean or clean in c:
                return product, 1.0, str(candidate)

    clean_words = set(clean.split())
    best, best_score, best_alias = None, 0.0, ""
    for product in products:
        candidates = [product.get("name", "")] + list(product.get("aliases", []) or [])
        for candidate in candidates:
            c = normalize_text(str(candidate))
            c_words = set(c.split())
            if not c_words:
                continue
            overlap = len(clean_words & c_words) / max(len(c_words), 1)
            score = max(overlap, similarity(clean, c))
            if score > best_score:
                best, best_score, best_alias = product, score, str(candidate)
    if best_score >= 0.75:
        return best, best_score, best_alias
    return None, best_score, best_alias


def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    for p in load_products():
        if p.get("id") == product_id:
            return p
    return None


def get_user_state(sender: str) -> Dict[str, Any]:
    states = read_json(USER_STATE_FILE, {})
    return states.get(sender, {}) if isinstance(states, dict) else {}


def set_user_state(sender: str, product: Optional[Dict[str, Any]]) -> None:
    states = read_json(USER_STATE_FILE, {})
    if not isinstance(states, dict):
        states = {}
    states[sender] = {
        "updated_at": now(),
        "last_product_id": product.get("id", "") if product else "",
        "last_product_name": product.get("name", "") if product else "",
    }
    write_json(USER_STATE_FILE, states)


def make_price_from_fields(price: str, price_strip: str, price_box: str) -> str:
    price = (price or "").strip()
    price_strip = (price_strip or "").strip()
    price_box = (price_box or "").strip()
    if price:
        return price
    parts = []
    if price_strip:
        parts.append(f"الشريط: {price_strip}")
    if price_box:
        parts.append(f"العلبة: {price_box}")
    return " | ".join(parts)


def safe_product_reply(product: Dict[str, Any]) -> str:
    name = product.get("name", "المنتج")
    price = product.get("price", "غير محدد")
    price_strip = str(product.get("price_strip", "")).strip()
    price_box = str(product.get("price_box", "")).strip()
    stock = str(product.get("stock", "غير محدد")).strip()
    quantity = str(product.get("quantity", "")).strip()

    if "غير" in stock or quantity == "0":
        return f"{greeting()}\n\n❌ المنتج غير متوفر حاليًا\nالمنتج: {name}"

    msg = f"{greeting()}\n\n✅ المنتج متوفر\nالمنتج: {name}"
    if price_strip or price_box:
        if price_strip:
            msg += f"\nسعر الشريط: {price_strip}"
        if price_box:
            msg += f"\nسعر العلبة: {price_box}"
    else:
        msg += f"\nالسعر: {price}"
    return msg.strip()


def transfer_reply() -> str:
    return f"{greeting()}\n\n✅ تم تحويل سؤالك للصيدلي.\nسيتم الرد عليك قريبًا."


def unknown_product_reply() -> str:
    return f"{greeting()}\n\n✅ وصل استفسارك.\nسيتم التأكد من توفر المنتج والرد عليك قريبًا."


def prescription_reply() -> str:
    return f"{greeting()}\n\n✅ وصلت الروشتة/الصورة.\nسيتم تحويلها للصيدلي للمراجعة والرد عليك قريبًا."


def send_whatsapp_text(to: str, body: str) -> Tuple[bool, str]:
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        append_log(SEND_LOG, f"{now()} | NO_TOKEN_OR_PHONE_ID | to={to} | BODY={body}")
        return False, "NO_TOKEN_OR_PHONE_ID"
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        append_log(SEND_LOG, f"{now()} | STATUS={r.status_code} | TO={to} | BODY={body} | RESPONSE={r.text}")
        return r.status_code < 300, r.text
    except Exception as e:
        append_log(SEND_LOG, f"{now()} | EXCEPTION={e} | TO={to} | BODY={body}")
        return False, str(e)


def save_pending(kind: str, sender: str, name: str, text: str = "", raw: Any = None, media_id: str = "", media_file: str = "", vision_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pending = read_json(PENDING_FILE, [])
    if not isinstance(pending, list):
        pending = []
    item = {
        "id": str(uuid.uuid4())[:8],
        "created_at": now(),
        "kind": kind,
        "from": sender,
        "name": name,
        "text": text,
        "media_id": media_id,
        "media_file": media_file,
        "status": "open",
        "vision_result": vision_result or {},
        "raw": raw or {},
    }
    pending.append(item)
    write_json(PENDING_FILE, pending)
    return item


def create_conversation_alert(sender: str, name: str, text: str, reason: str, product: Optional[Dict[str, Any]] = None, raw: Any = None, media_id: str = "", media_file: str = "", vision_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    conversations = read_json(CONVERSATIONS_FILE, [])
    if not isinstance(conversations, list):
        conversations = []
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
        "media_file": media_file,
        "vision_result": vision_result or {},
        "messages": [{"time": now(), "role": "customer", "text": text}],
        "raw": raw or {},
    }
    conversations.append(item)
    write_json(CONVERSATIONS_FILE, conversations)
    return item


def update_conversation_status(conv_id: str, status: str, admin_reply: str = "", send_result: str = "") -> bool:
    conversations = read_json(CONVERSATIONS_FILE, [])
    if not isinstance(conversations, list):
        return False
    changed = False
    for conv in conversations:
        if conv.get("id") == conv_id:
            if admin_reply:
                conv.setdefault("messages", []).append({"time": now(), "role": "admin", "text": admin_reply})
            conv["status"] = status
            conv["updated_at"] = now()
            if send_result:
                conv["last_send_result"] = send_result[:1000]
            changed = True
            break
    if changed:
        write_json(CONVERSATIONS_FILE, conversations)
    return changed


def extract_messages(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for entry in data.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            contacts = value.get("contacts", []) or []
            contact_name = ""
            if contacts:
                contact_name = contacts[0].get("profile", {}).get("name", "")
            for msg in value.get("messages", []) or []:
                msg_type = msg.get("type", "")
                text, media_id = "", ""
                if msg_type == "text":
                    text = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    media_id = msg.get("image", {}).get("id", "")
                    text = msg.get("image", {}).get("caption", "")
                elif msg_type == "document":
                    media_id = msg.get("document", {}).get("id", "")
                    text = msg.get("document", {}).get("caption", "") or msg.get("document", {}).get("filename", "")
                out.append({"from": msg.get("from", ""), "name": contact_name, "type": msg_type, "text": text, "media_id": media_id, "raw": msg})
    return out


def ai_find_product_from_text(text: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    if not TEXT_AI_ENABLED or resolve_product_from_text_ai is None:
        return None, {"success": False, "error": "text_ai_disabled_or_unavailable"}
    products = load_products()
    result = resolve_product_from_text_ai(text, products)
    append_log(TEXT_AI_LOG, f"{now()} | TEXT={text} | RESULT={json.dumps(result, ensure_ascii=False)}")
    if not result.get("success") or result.get("needs_admin"):
        return None, result
    try:
        confidence = float(result.get("confidence") or 0)
    except Exception:
        confidence = 0.0
    if confidence < TEXT_AI_MIN_CONFIDENCE:
        return None, result
    # Prefer matched_id when the model returns a product id from our list.
    matched_id = str(result.get("matched_id", "")).strip()
    if matched_id:
        product = get_product_by_id(matched_id)
        if product:
            return product, result
    product_name = str(result.get("product_name", "")).strip()
    if not product_name:
        return None, result
    product, score, alias = find_product(product_name)
    result["local_match_score"] = score
    result["local_match_alias"] = alias
    if product and score >= 0.75:
        return product, result
    return None, result


def handle_text(sender: str, name: str, text: str, raw: Any = None) -> None:
    product, _, _ = find_product(text)
    if has_detail_question(text):
        if not product:
            state = get_user_state(sender)
            product = get_product_by_id(state.get("last_product_id", ""))
        create_conversation_alert(sender, name, text, "details_or_pharmacist_needed", product=product, raw=raw)
        send_whatsapp_text(sender, transfer_reply())
        return
    if product:
        set_user_state(sender, product)
        send_whatsapp_text(sender, safe_product_reply(product))
        return

    ai_product, ai_result = ai_find_product_from_text(text)
    if ai_product:
        set_user_state(sender, ai_product)
        send_whatsapp_text(sender, safe_product_reply(ai_product))
        return

    save_pending("unknown_text", sender, name, text=text, raw=raw, vision_result={"text_ai_result": ai_result})
    create_conversation_alert(sender, name, text, "unknown_product", raw=raw, vision_result={"text_ai_result": ai_result})
    send_whatsapp_text(sender, unknown_product_reply())


def download_whatsapp_media(media_id: str) -> Tuple[Optional[bytes], str, str]:
    if not media_id or not WHATSAPP_TOKEN:
        return None, "", "NO_MEDIA_ID_OR_TOKEN"
    try:
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        meta_url = f"https://graph.facebook.com/v25.0/{media_id}"
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


def save_media_file(media_id: str, data: bytes, mime_type: str) -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", media_id or str(uuid.uuid4())[:8])
    ext = ".jpg"
    if "png" in (mime_type or ""):
        ext = ".png"
    elif "webp" in (mime_type or ""):
        ext = ".webp"
    elif "pdf" in (mime_type or ""):
        ext = ".pdf"
    filename = f"{safe_id}{ext}"
    (MEDIA_DIR / filename).write_bytes(data)
    return filename


def strict_match_is_safe(vision_result: Dict[str, Any], product: Optional[Dict[str, Any]], match_score: float) -> Tuple[bool, str]:
    if not vision_result.get("success"):
        return False, "vision_failed"
    if str(vision_result.get("image_type", "")).lower() in {"prescription", "rx", "medical_prescription"}:
        return False, "prescription_always_admin"
    if not product:
        return False, "product_not_found"
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
        guessed = normalize_text(str(vision_result.get("product_name", "")))
        possible = [normalize_text(str(product.get("name", "")))] + [normalize_text(str(a)) for a in product.get("aliases", []) or []]
        if not any(p and (p == guessed or p in guessed or guessed in p) for p in possible):
            return False, "not_exact_enough"
    return True, "safe"


def handle_image(sender: str, name: str, text: str, media_id: str, raw: Any) -> None:
    if has_prescription_words(text):
        create_conversation_alert(sender, name, text or "روشتة/صورة تحتاج مراجعة", "prescription_caption", raw=raw, media_id=media_id)
        send_whatsapp_text(sender, prescription_reply())
        return
    image_bytes, mime_type, media_error = download_whatsapp_media(media_id)
    media_file = ""
    if not image_bytes:
        vision_result = {"success": False, "error": media_error}
        append_log(VISION_LOG, f"{now()} | MEDIA_ERROR | {json.dumps(vision_result, ensure_ascii=False)}")
        save_pending("image_download_failed", sender, name, text=text, media_id=media_id, raw=raw, vision_result=vision_result)
        create_conversation_alert(sender, name, text or "صورة تحتاج مراجعة", "image_download_failed", raw=raw, media_id=media_id)
        send_whatsapp_text(sender, prescription_reply())
        return
    try:
        media_file = save_media_file(media_id, image_bytes, mime_type)
    except Exception:
        media_file = ""
    if not VISION_ENABLED or analyze_image_with_fallback is None:
        save_pending("image", sender, name, text=text, media_id=media_id, raw=raw, media_file=media_file)
        create_conversation_alert(sender, name, text or "صورة منتج", "image_needs_review", raw=raw, media_id=media_id, media_file=media_file)
        send_whatsapp_text(sender, prescription_reply())
        return
    products = load_products()
    vision_result = analyze_image_with_fallback(image_bytes=image_bytes, mime_type=mime_type or "image/jpeg", caption=text or "", products=products)
    append_log(VISION_LOG, f"{now()} | RESULT | {json.dumps(vision_result, ensure_ascii=False)}")
    if str(vision_result.get("image_type", "")).lower() in {"prescription", "rx", "medical_prescription"}:
        save_pending("prescription_image", sender, name, text=text, media_id=media_id, raw=raw, media_file=media_file, vision_result=vision_result)
        create_conversation_alert(sender, name, text or "روشتة تحتاج مراجعة", "prescription_image", raw=raw, media_id=media_id, media_file=media_file, vision_result=vision_result)
        send_whatsapp_text(sender, prescription_reply())
        return
    guess_text = " ".join(str(vision_result.get(k, "")) for k in ("product_name", "brand", "visible_text", "generic_name"))
    product, score, _ = find_product(f"{text} {guess_text}")
    safe, reason = strict_match_is_safe(vision_result, product, score)
    if safe:
        set_user_state(sender, product)
        send_whatsapp_text(sender, safe_product_reply(product))
        return
    vision_result["strict_decision"] = "sent_to_admin"
    vision_result["strict_reason"] = reason
    vision_result["match_score"] = score
    vision_result["matched_product_id"] = product.get("id") if product else ""
    save_pending("image_needs_review", sender, name, text=text, media_id=media_id, raw=raw, media_file=media_file, vision_result=vision_result)
    create_conversation_alert(sender, name, text or "صورة منتج تحتاج مراجعة", "image_needs_review", product=product, raw=raw, media_id=media_id, media_file=media_file, vision_result=vision_result)
    send_whatsapp_text(sender, f"{greeting()}\n\n✅ وصلت الصورة.\nسيتم التأكد من المنتج والرد عليك قريبًا.")


def admin_ok() -> bool:
    return request.args.get("token") == ADMIN_TOKEN


def admin_link(endpoint: str = "admin_dashboard", **params: str) -> str:
    params["token"] = ADMIN_TOKEN
    return url_for(endpoint, **params)


@app.get("/")
def home():
    return jsonify({"status": "running", "name": "WhatsPriceBot V4.3 Inventory Sync Safe", "time": now(), "pharmacy_name": PHARMACY_NAME})


@app.get("/health")
def health():
    conversations = read_json(CONVERSATIONS_FILE, [])
    if not isinstance(conversations, list):
        conversations = []
    open_count = len([c for c in conversations if c.get("status") == "open"])
    sync_status = get_sync_status()
    return jsonify({
        "ok": True,
        "products": len(load_products()),
        "pending": len(read_json(PENDING_FILE, [])),
        "open_conversations": open_count,
        "phone_number_id_loaded": bool(PHONE_NUMBER_ID),
        "token_loaded": bool(WHATSAPP_TOKEN),
        "vision_enabled": VISION_ENABLED,
        "text_ai_enabled": TEXT_AI_ENABLED and resolve_product_from_text_ai is not None,
        "inventory_sync_enabled": bool(INVENTORY_SYNC_TOKEN),
        "inventory_last_sync_at": sync_status.get("last_sync_at", ""),
        "inventory_products_count": sync_status.get("products_count", 0),
        "inventory_last_error": sync_status.get("last_error", ""),
    })


ADMIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root{--main:#128c7e;--bg:#f4f6f8;--card:#fff;--danger:#c0392b;--muted:#687076}
    body{font-family:Arial,Tahoma,sans-serif;background:var(--bg);margin:0;color:#1f2933}
    .wrap{max-width:1100px;margin:auto;padding:12px}
    header{background:#075e54;color:white;padding:14px;border-radius:0 0 16px 16px;position:sticky;top:0;z-index:5}
    h1{font-size:20px;margin:0 0 6px}.subtitle{font-size:13px;opacity:.9}
    .nav{display:flex;gap:8px;overflow:auto;margin:12px 0}.nav a{background:#e7f6f3;color:#075e54;padding:10px 12px;border-radius:12px;text-decoration:none;white-space:nowrap;font-weight:bold}
    .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.stat{background:var(--card);border-radius:16px;padding:14px;box-shadow:0 2px 8px #0001}.stat b{font-size:28px;color:var(--main);display:block}
    .card{background:var(--card);border-radius:16px;padding:14px;margin:12px 0;box-shadow:0 2px 8px #0001;overflow:auto}
    .ticket{border:1px solid #eee;border-radius:14px;padding:12px;margin:10px 0;background:#fffdfd}.ticket-head{display:flex;justify-content:space-between;color:var(--danger);font-weight:bold}.msg{background:#f7f7f7;padding:10px;border-radius:10px;white-space:pre-wrap}
    input,textarea,select{width:100%;box-sizing:border-box;padding:11px;margin:6px 0;border:1px solid #d5d8dc;border-radius:12px;font-size:15px;background:white}textarea{min-height:90px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.btn,button{background:var(--main);color:white;border:0;border-radius:12px;padding:10px 13px;text-decoration:none;display:inline-block;cursor:pointer;font-weight:bold}.btn.secondary,button.secondary{background:#777}.btn.danger,button.danger{background:var(--danger)}.btn.light{background:#e7f6f3;color:#075e54}
    table{width:100%;border-collapse:collapse;min-width:920px;font-size:14px}th,td{border-bottom:1px solid #e6e6e6;padding:9px;text-align:right;vertical-align:top}th{background:#f1f3f5}.ok{color:green;font-weight:bold}.small{font-size:12px;color:var(--muted)}
    img.preview{max-width:240px;border-radius:12px;border:1px solid #ddd}
  </style>
</head>
<body>
<header><div class="wrap"><h1>{{ title }}</h1><div class="subtitle">{{ pharmacy_name }}</div></div></header>
<div class="wrap">
  <div class="nav">
    <a href="#inbox">🔔 الطلبات</a><a href="#sync">🔄 المزامنة</a><a href="#add">➕ إضافة منتج</a><a href="#products">💊 المنتجات</a><a href="{{ admin_url }}">تحديث</a>
  </div>
  <div class="stats">
    <div class="stat">طلبات تحتاج رد <b>{{ open_conversations|length }}</b></div>
    <div class="stat">المنتجات <b>{{ products|length }}</b></div>
    <div class="stat">مراجعات <b>{{ pending_count }}</b></div>
    <div class="stat">آخر مزامنة <b style="font-size:16px">{{ sync_status.get('last_sync_at','لا يوجد') or 'لا يوجد' }}</b></div>
  </div>


  <section id="sync" class="card">
    <h2>🔄 حالة مزامنة المخزون</h2>
    {% if sync_enabled %}
      <p class="ok">✅ رابط المزامنة مفعّل بمفتاح خاص من ملف .env</p>
    {% else %}
      <p style="color:#c0392b;font-weight:bold">⚠️ رابط المزامنة غير مفعّل. أضف INVENTORY_SYNC_TOKEN في ملف .env.</p>
    {% endif %}
    <div class="grid">
      <div><b>آخر تحديث:</b><br>{{ sync_status.get('last_sync_at','لا يوجد') or 'لا يوجد' }}</div>
      <div><b>عدد المنتجات المستلمة:</b><br>{{ sync_status.get('products_count', 0) }}</div>
      <div><b>المصدر:</b><br>{{ sync_status.get('source','غير محدد') or 'غير محدد' }}</div>
      <div><b>Backup:</b><br>{{ sync_status.get('backup_file','') or 'لا يوجد' }}</div>
    </div>
    {% if sync_status.get('last_error') %}
      <p style="color:#c0392b"><b>آخر خطأ:</b> {{ sync_status.get('last_error') }}</p>
    {% endif %}
    <p class="small">Endpoint للبرنامج الخارجي: <b>POST /api/sync_inventory</b>. لا يظهر المفتاح هنا لحمايته.</p>
  </section>

  <section id="inbox" class="card">
    <h2>🔔 إشعارات تحتاج رد</h2>
    {% if not open_conversations %}<p class="ok">لا توجد طلبات تحتاج رد حاليًا ✅</p>{% endif %}
    {% for c in open_conversations %}
      <div class="ticket">
        <div class="ticket-head"><span>🔴 يحتاج رد</span><span>{{ c.updated_at }}</span></div>
        <p><b>الزبون:</b> {{ c['from'] }} — {{ c.name }}</p>
        <p><b>السبب:</b> {{ c.reason }}</p>
        {% if c.last_product %}<p><b>آخر منتج:</b> {{ c.last_product }}</p>{% endif %}
        <p class="msg">{{ c.messages[-1].text if c.messages else '' }}</p>
        {% if c.media_file %}<p><b>الصورة:</b></p><img class="preview" src="{{ url_for('admin_media', filename=c.media_file, token=token) }}">{% endif %}
        {% if c.vision_result %}<p class="small">توقع الصورة: {{ c.vision_result.get('product_name','') }} | سبب التحويل: {{ c.vision_result.get('strict_reason') or c.vision_result.get('error','') }}</p>{% endif %}
        <form method="post" action="{{ url_for('admin_reply', token=token) }}">
          <input type="hidden" name="conv_id" value="{{ c.id }}">
          <textarea name="reply" placeholder="اكتب رد الصيدلية هنا..." required></textarea>
          <button type="submit">إرسال للزبون</button>
        </form>
        <form method="post" action="{{ url_for('admin_close', token=token) }}">
          <input type="hidden" name="conv_id" value="{{ c.id }}">
          <button class="secondary" type="submit">إغلاق بدون رد</button>
        </form>
      </div>
    {% endfor %}
  </section>

  <section id="add" class="card">
    <h2>➕ إضافة منتج</h2>
    <form method="post" action="{{ url_for('admin_add_product', token=token) }}">
      <div class="grid">
        <input name="id" placeholder="id مثل panadol_500" required>
        <input name="category" placeholder="القسم">
        <input name="name" placeholder="اسم المنتج" required>
        <input name="price" placeholder="السعر العام اختياري">
        <input name="price_strip" placeholder="سعر الشريط مثل: 8 د.ل">
        <input name="price_box" placeholder="سعر العلبة مثل: 16 د.ل">
        <input name="strips_count" placeholder="عدد الشرائط مثل: 12">
        <select name="stock"><option value="متوفر">متوفر</option><option value="غير متوفر">غير متوفر</option></select>
        <input name="quantity" placeholder="الكمية">
      </div>
      <input name="aliases" placeholder="أسماء بديلة مفصولة بفواصل: بندول, بانادول, panadol">
      <button type="submit">حفظ المنتج</button>
    </form>
  </section>

  <section id="products" class="card">
    <h2>💊 المنتجات</h2>
    <table>
      <tr><th>ID</th><th>القسم</th><th>الاسم</th><th>السعر العام</th><th>سعر الشريط</th><th>سعر العلبة</th><th>عدد الشرائط</th><th>التوفر</th><th>الكمية</th><th>تعديل</th><th>الأسماء البديلة</th></tr>
      {% for prod in products %}
      <tr>
        <td>{{ prod.id }}</td><td>{{ prod.category }}</td><td>{{ prod.name }}</td><td>{{ prod.price }}</td><td>{{ prod.price_strip }}</td><td>{{ prod.price_box }}</td><td>{{ prod.strips_count }}</td><td>{{ prod.stock }}</td><td>{{ prod.quantity }}</td>
        <td><a class="btn light" href="{{ url_for('admin_edit_product', token=token, id=prod.id) }}">تعديل</a></td>
        <td>{{ (prod.aliases or [])|join(', ') }}</td>
      </tr>
      {% endfor %}
    </table>
  </section>
</div>
</body>
</html>
"""

EDIT_TEMPLATE = """
<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>تعديل منتج</title>
<style>body{font-family:Arial;background:#f4f6f8;margin:0}.wrap{max-width:780px;margin:auto;padding:14px}.card{background:white;border-radius:16px;padding:16px;box-shadow:0 2px 8px #0001}input,textarea,select{width:100%;box-sizing:border-box;padding:11px;margin:6px 0;border:1px solid #d5d8dc;border-radius:12px;font-size:15px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.btn,button{background:#128c7e;color:white;border:0;border-radius:12px;padding:10px 13px;text-decoration:none;display:inline-block;cursor:pointer;font-weight:bold}.danger{background:#c0392b}.secondary{background:#777}</style>
</head><body><div class="wrap"><div class="card"><h2>تعديل المنتج</h2>
<form method="post" action="{{ url_for('admin_update_product', token=token) }}">
<input type="hidden" name="id" value="{{ product.id }}">
<label>اسم المنتج</label><input name="name" value="{{ product.name }}" required>
<div class="grid"><input name="category" placeholder="القسم" value="{{ product.category }}"><input name="price" placeholder="السعر العام" value="{{ product.price }}"><input name="price_strip" placeholder="سعر الشريط" value="{{ product.price_strip }}"><input name="price_box" placeholder="سعر العلبة" value="{{ product.price_box }}"><input name="strips_count" placeholder="عدد الشرائط" value="{{ product.strips_count }}"><input name="quantity" placeholder="الكمية" value="{{ product.quantity }}"><select name="stock"><option value="متوفر" {% if product.stock == 'متوفر' %}selected{% endif %}>متوفر</option><option value="غير متوفر" {% if product.stock != 'متوفر' %}selected{% endif %}>غير متوفر</option></select></div>
<label>أسماء بديلة</label><textarea name="aliases">{{ (product.aliases or [])|join(', ') }}</textarea>
<button type="submit">حفظ</button> <a class="btn secondary" href="{{ url_for('admin_dashboard', token=token) }}">رجوع</a>
</form>
<form method="post" action="{{ url_for('admin_quick_stock', token=token) }}"><input type="hidden" name="id" value="{{ product.id }}"><button name="stock" value="متوفر">✅ متوفر</button> <button class="danger" name="stock" value="غير متوفر">❌ غير متوفر</button></form>
</div></div></body></html>
"""


@app.get("/admin/media/<filename>")
def admin_media(filename: str):
    if not admin_ok():
        return "Forbidden", 403
    return send_from_directory(MEDIA_DIR, filename)


@app.get("/admin")
def admin_dashboard():
    if not admin_ok():
        return "Forbidden", 403
    products = load_products()
    pending = read_json(PENDING_FILE, [])
    conversations = read_json(CONVERSATIONS_FILE, [])
    if not isinstance(conversations, list):
        conversations = []
    open_conversations = sorted([c for c in conversations if c.get("status") == "open"], key=lambda x: x.get("updated_at", ""), reverse=True)
    return render_template_string(
        ADMIN_TEMPLATE,
        title=ADMIN_PANEL_TITLE,
        pharmacy_name=PHARMACY_NAME,
        products=products,
        open_conversations=open_conversations,
        pending_count=len(pending) if isinstance(pending, list) else 0,
        sync_status=get_sync_status(),
        sync_enabled=bool(INVENTORY_SYNC_TOKEN),
        token=ADMIN_TOKEN,
        admin_url=admin_link("admin_dashboard"),
    )


@app.get("/admin/edit_product")
def admin_edit_product():
    if not admin_ok():
        return "Forbidden", 403
    product = get_product_by_id(request.args.get("id", ""))
    if not product:
        return "Product not found", 404
    return render_template_string(EDIT_TEMPLATE, product=product, token=ADMIN_TOKEN)


def product_from_form(product_id: str) -> Dict[str, Any]:
    price_strip = request.form.get("price_strip", "").strip()
    price_box = request.form.get("price_box", "").strip()
    price = make_price_from_fields(request.form.get("price", "").strip(), price_strip, price_box)
    aliases = [x.strip() for x in request.form.get("aliases", "").split(",") if x.strip()]
    return {
        "id": product_id,
        "category": request.form.get("category", "").strip(),
        "name": request.form.get("name", "").strip(),
        "price": price,
        "price_strip": price_strip,
        "price_box": price_box,
        "strips_count": request.form.get("strips_count", "").strip(),
        "stock": request.form.get("stock", "متوفر").strip(),
        "quantity": request.form.get("quantity", "").strip(),
        "expiry_date": request.form.get("expiry_date", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "aliases": aliases,
    }


@app.post("/admin/add_product")
def admin_add_product():
    if not admin_ok():
        return "Forbidden", 403
    product_id = request.form.get("id", "").strip()
    if not product_id:
        return "Missing product id", 400
    item = product_from_form(product_id)
    products = load_products()
    for i, p in enumerate(products):
        if p.get("id") == product_id:
            old_aliases = p.get("aliases", []) or []
            for a in old_aliases:
                if a not in item["aliases"]:
                    item["aliases"].append(a)
            products[i] = item
            break
    else:
        products.append(item)
    save_products(products)
    return redirect(admin_link("admin_dashboard"))


@app.post("/admin/update_product")
def admin_update_product():
    if not admin_ok():
        return "Forbidden", 403
    product_id = request.form.get("id", "").strip()
    item = product_from_form(product_id)
    products = load_products()
    for i, p in enumerate(products):
        if p.get("id") == product_id:
            products[i] = item
            save_products(products)
            return redirect(admin_link("admin_dashboard"))
    return "Product not found", 404


@app.post("/admin/quick_stock")
def admin_quick_stock():
    if not admin_ok():
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
            return redirect(admin_link("admin_dashboard"))
    return "Product not found", 404


@app.post("/admin/reply")
def admin_reply():
    if not admin_ok():
        return "Forbidden", 403
    conv_id = request.form.get("conv_id", "").strip()
    reply = request.form.get("reply", "").strip()
    conversations = read_json(CONVERSATIONS_FILE, [])
    conv = None
    if isinstance(conversations, list):
        conv = next((c for c in conversations if c.get("id") == conv_id), None)
    if not conv:
        return "Conversation not found", 404
    if not reply:
        return "Reply is empty", 400
    ok, resp = send_whatsapp_text(conv.get("from", ""), reply)
    update_conversation_status(conv_id, "closed" if ok else "send_failed", admin_reply=reply, send_result=str(resp))
    return redirect(admin_link("admin_dashboard"))


@app.post("/admin/close")
def admin_close():
    if not admin_ok():
        return "Forbidden", 403
    update_conversation_status(request.form.get("conv_id", "").strip(), "closed")
    return redirect(admin_link("admin_dashboard"))


@app.get("/api/sync_status")
def api_sync_status():
    if not (sync_auth_ok() or admin_ok()):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    status = get_sync_status()
    return jsonify({"ok": True, "sync_enabled": bool(INVENTORY_SYNC_TOKEN), "status": status, "products": len(load_products())})


@app.post("/api/sync_inventory")
def api_sync_inventory():
    if not INVENTORY_SYNC_TOKEN:
        return jsonify({"ok": False, "error": "INVENTORY_SYNC_TOKEN is not configured on server"}), 503
    if not sync_auth_ok():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"ok": False, "error": "Invalid or missing JSON body"}), 400
    ok, status = apply_inventory_sync(payload)
    code = 200 if ok else 400
    return jsonify(status), code


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
    for msg in extract_messages(data):
        sender, name, msg_type = msg["from"], msg["name"], msg["type"]
        if msg_type == "text":
            handle_text(sender, name, msg["text"], raw=msg["raw"])
        elif msg_type == "image":
            handle_image(sender, name, msg["text"], msg["media_id"], msg["raw"])
        elif msg_type == "document":
            create_conversation_alert(sender, name, msg["text"] or "ملف/روشتة تحتاج مراجعة", "document_or_prescription", raw=msg["raw"], media_id=msg["media_id"])
            send_whatsapp_text(sender, prescription_reply())
        else:
            save_pending("unsupported", sender, name, raw=msg["raw"])
            create_conversation_alert(sender, name, "رسالة تحتاج مراجعة", "unsupported_message", raw=msg["raw"])
            send_whatsapp_text(sender, f"{greeting()}\n\n✅ وصلت رسالتك.\nسيتم تحويلها للصيدلي للرد عليك.")
    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    ensure_products()
    app.run(host="0.0.0.0", port=PORT)
