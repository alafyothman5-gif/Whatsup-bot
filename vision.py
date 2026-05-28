#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vision fallback module for WhatsPriceBot."""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Dict, List

import requests


def _json_from_text(text: str) -> Dict[str, Any]:
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


def _product_context(products: List[Dict[str, Any]]) -> str:
    limit = int(os.getenv("VISION_INCLUDE_PRODUCTS_LIMIT", "80"))
    lines = []
    for p in (products or [])[:limit]:
        aliases = ", ".join((p.get("aliases") or [])[:6])
        lines.append(f"- {p.get('name','')} | aliases: {aliases}")
    if not lines:
        return ""
    return "قائمة منتجات محتملة من قاعدة البيانات:\n" + "\n".join(lines)


def _prompt(caption: str, products: List[Dict[str, Any]]) -> str:
    context = _product_context(products)
    return f"""
أنت مساعد يتعرف على صورة مرسلة لصيدلية عبر واتساب.

قواعد صارمة:
- إذا الصورة روشتة/وصفة طبية/ورقة دكتور/قائمة أدوية مكتوبة، اجعل image_type = "prescription".
- إذا الصورة علبة دواء واضحة، اجعل image_type = "medicine_package".
- لو لست متأكدًا جدًا جدًا، اجعل confidence أقل من 0.995.
- لا تعطِ ثقة عالية إلا لو اسم المنتج واضح جدًا بالصورة.
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


def _success(provider: str, data: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
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


def _fail(provider: str, error: Any) -> Dict[str, Any]:
    return {"success": False, "provider": provider, "error": str(error)[:1000]}


def _call_gemini(api_key: str, image_bytes: bytes, mime_type: str, caption: str, products: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "contents": [{"parts": [{"text": _prompt(caption, products)}, {"inline_data": {"mime_type": mime_type or "image/jpeg", "data": b64}}]}],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"},
    }
    r = requests.post(url, json=payload, timeout=45)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        text = json.dumps(data, ensure_ascii=False)
    parsed = _json_from_text(text)
    if not parsed:
        raise RuntimeError(f"No JSON parsed from Gemini response: {text[:600]}")
    return _success(label, parsed, text)


def _call_openrouter(image_bytes: bytes, mime_type: str, caption: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY missing")
    model = os.getenv("OPENROUTER_VISION_MODEL", "qwen/qwen2.5-vl-72b-instruct:free")
    data_url = f"data:{mime_type or 'image/jpeg'};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [{"type": "text", "text": _prompt(caption, products)}, {"type": "image_url", "image_url": {"url": data_url}}]}],
        "temperature": 0.0,
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
    parsed = _json_from_text(str(text))
    if not parsed:
        raise RuntimeError(f"No JSON parsed from OpenRouter response: {str(text)[:600]}")
    return _success("openrouter", parsed, str(text))


def _call_xai(image_bytes: bytes, mime_type: str, caption: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.getenv("XAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("XAI_API_KEY missing")
    model = os.getenv("XAI_VISION_MODEL", "grok-4.3")
    data_url = f"data:{mime_type or 'image/jpeg'};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [{"type": "text", "text": _prompt(caption, products)}, {"type": "image_url", "image_url": {"url": data_url}}]}],
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _json_from_text(str(text))
    if not parsed:
        raise RuntimeError(f"No JSON parsed from xAI response: {str(text)[:600]}")
    return _success("grok", parsed, str(text))


def analyze_image_with_fallback(image_bytes: bytes, mime_type: str, caption: str = "", products: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    products = products or []
    order = os.getenv("VISION_PROVIDER_ORDER", "gemini1,openrouter,grok")
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
            if provider in {"grok", "xai"}:
                return _call_xai(image_bytes, mime_type, caption, products)
            errors.append(_fail(provider, "unknown provider"))
        except Exception as e:
            errors.append(_fail(provider, e))
            continue
    return {"success": False, "provider": "none", "error": "all vision providers failed", "errors": errors}
