#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import json
import os
import re
import requests


def _json_from_text(text):
    if not text:
        return {}

    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}

    return {}


def _product_context(products):
    limit = int(os.getenv("VISION_INCLUDE_PRODUCTS_LIMIT", "80"))
    if limit <= 0:
        return ""

    lines = []
    for p in products[:limit]:
        aliases = ", ".join(p.get("aliases", [])[:6])
        line = f"- {p.get('name','')} | aliases: {aliases}"
        lines.append(line)

    if not lines:
        return ""

    return "قائمة منتجات محتملة من قاعدة البيانات:\n" + "\n".join(lines)


def _prompt(caption, products):
    context = _product_context(products)
    return f"""
أنت مساعد يتعرف على صورة مرسلة لصيدلية عبر واتساب.

قواعد صارمة:
- إذا الصورة روشتة/وصفة طبية/ورقة دكتور/قائمة أدوية مكتوبة، اجعل image_type = "prescription" ولا تستخرج سعرًا.
- إذا الصورة علبة دواء واضحة، اجعل image_type = "medicine_package".
- لو لست متأكدًا جدًا جدًا، اجعل confidence أقل من 0.995.
- لا تعطِ ثقة عالية إلا لو اسم المنتج واضح جدًا بالصورة.
- استخرج اسم المنتج فقط إذا كان واضحًا.
- لا تعطِ جرعة ولا نصيحة طبية.
- لا تخترع سعر أو توفر.
- أعد JSON فقط، بدون شرح.

شكل JSON:
{{
  "image_type": "medicine_package أو prescription أو unknown",
  "product_name": "اسم المنتج الأقرب إن كان واضحًا",
  "brand": "الشركة/العلامة إن ظهرت",
  "generic_name": "الاسم العلمي إن كان دواء وظهر",
  "visible_text": "أي نص واضح على الصورة",
  "confidence": 0.0,
  "notes": "ملاحظة قصيرة"
}}

تعليق العميل على الصورة:
{caption or ""}

{context}
""".strip()


def _success(provider, data, raw_text=""):
    return {
        "success": True,
        "provider": provider,
        "image_type": data.get("image_type", "unknown"),
        "product_name": data.get("product_name", "") or data.get("name", ""),
        "brand": data.get("brand", ""),
        "generic_name": data.get("generic_name", ""),
        "visible_text": data.get("visible_text", ""),
        "confidence": data.get("confidence", 0),
        "notes": data.get("notes", ""),
        "raw_text": raw_text[:1000],
    }


def _fail(provider, error):
    return {
        "success": False,
        "provider": provider,
        "error": str(error)[:1000],
    }


def _call_gemini(api_key, image_bytes, mime_type, caption, products, label):
    model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = _prompt(caption, products)
    b64 = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type or "image/jpeg",
                            "data": b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "response_mime_type": "application/json"
        }
    }

    r = requests.post(url, json=payload, timeout=45)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")

    data = r.json()
    text = ""
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        text = json.dumps(data, ensure_ascii=False)

    parsed = _json_from_text(text)
    if not parsed:
        raise RuntimeError(f"No JSON parsed from Gemini response: {text[:600]}")

    return _success(label, parsed, text)


def _call_openrouter(image_bytes, mime_type, caption, products):
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_VISION_MODEL", "qwen/qwen2.5-vl-72b-instruct:free")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    prompt = _prompt(caption, products)
    data_url = f"data:{mime_type or 'image/jpeg'};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.0
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://example.com"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "WhatsPriceBot"),
    }

    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")

    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(text, list):
        text = " ".join(str(x) for x in text)
    parsed = _json_from_text(text)
    if not parsed:
        raise RuntimeError(f"No JSON parsed from OpenRouter response: {str(text)[:600]}")

    return _success("openrouter", parsed, str(text))


def _call_xai_grok(image_bytes, mime_type, caption, products):
    api_key = os.getenv("XAI_API_KEY", "")
    model = os.getenv("XAI_VISION_MODEL", "grok-4.3")
    if not api_key:
        raise RuntimeError("XAI_API_KEY missing")

    prompt = _prompt(caption, products)
    data_url = f"data:{mime_type or 'image/jpeg'};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.0
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    r = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")

    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _json_from_text(text)
    if not parsed:
        raise RuntimeError(f"No JSON parsed from xAI response: {str(text)[:600]}")

    return _success("grok", parsed, str(text))


def _call_cloudflare(image_bytes, mime_type, caption, products):
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    model = os.getenv("CLOUDFLARE_VISION_MODEL", "@cf/meta/llama-3.2-11b-vision-instruct")

    if not account_id or not api_token:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN missing")

    prompt = _prompt(caption, products)
    b64 = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt}
        ],
        "image": b64
    }

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")

    data = r.json()
    result = data.get("result", data)
    text = ""
    if isinstance(result, dict):
        text = result.get("response") or result.get("text") or result.get("content") or json.dumps(result, ensure_ascii=False)
    else:
        text = str(result)

    parsed = _json_from_text(text)
    if not parsed:
        raise RuntimeError(f"No JSON parsed from Cloudflare response: {text[:600]}")

    return _success("cloudflare", parsed, text)


def analyze_image_with_fallback(image_bytes, mime_type, caption="", products=None):
    products = products or []

    order = os.getenv(
        "VISION_PROVIDER_ORDER",
        "gemini1,gemini2,openrouter,cloudflare,grok"
    )
    providers = [x.strip().lower() for x in order.split(",") if x.strip()]

    errors = []

    for provider in providers:
        try:
            if provider == "gemini1":
                key = os.getenv("GEMINI_API_KEY_1", "")
                if not key:
                    errors.append(_fail(provider, "GEMINI_API_KEY_1 missing"))
                    continue
                return _call_gemini(key, image_bytes, mime_type, caption, products, "gemini1")

            if provider == "gemini2":
                key = os.getenv("GEMINI_API_KEY_2", "")
                if not key:
                    errors.append(_fail(provider, "GEMINI_API_KEY_2 missing"))
                    continue
                return _call_gemini(key, image_bytes, mime_type, caption, products, "gemini2")

            if provider == "openrouter":
                return _call_openrouter(image_bytes, mime_type, caption, products)

            if provider == "cloudflare":
                return _call_cloudflare(image_bytes, mime_type, caption, products)

            if provider in ("grok", "xai"):
                return _call_xai_grok(image_bytes, mime_type, caption, products)

            errors.append(_fail(provider, "unknown provider"))

        except Exception as e:
            errors.append(_fail(provider, e))
            continue

    return {
        "success": False,
        "provider": "none",
        "error": "all vision providers failed",
        "errors": errors
    }
