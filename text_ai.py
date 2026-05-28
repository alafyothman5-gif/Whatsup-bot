#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Text AI fallback for WhatsPriceBot.

This module only identifies the product name the customer is asking about.
It never invents price, stock, dosage, or medical advice.
"""
from __future__ import annotations

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


def _products_context(products: List[Dict[str, Any]]) -> str:
    limit = int(os.getenv("TEXT_AI_INCLUDE_PRODUCTS_LIMIT", "250"))
    lines = []
    for p in (products or [])[:limit]:
        aliases = ", ".join(str(x) for x in (p.get("aliases") or [])[:8])
        lines.append(f"- id={p.get('id','')} | name={p.get('name','')} | aliases={aliases}")
    return "\n".join(lines)


def _prompt(customer_text: str, products: List[Dict[str, Any]]) -> str:
    context = _products_context(products)
    return f"""
أنت جزء من بوت صيدلية. مهمتك الوحيدة: استخراج اسم المنتج الذي يسأل عنه الزبون من الرسالة.

قواعد صارمة:
- لا تعطِ جرعات أو نصائح طبية.
- لا تخترع منتجًا غير موجود في قائمة المنتجات.
- إذا كانت الرسالة عن جرعة/حامل/طفل/ضغط/سكر/بديل/استعمال/حساسية/روشتة، اجعل needs_admin=true.
- إذا لم تجد منتجًا واضحًا من القائمة، اجعل confidence أقل من 0.70 و product_name فارغًا.
- أعد JSON فقط بدون شرح.

شكل JSON:
{{
  "product_name": "اسم المنتج المطابق من القائمة أو فارغ",
  "matched_id": "id المنتج من القائمة إن عرفته أو فارغ",
  "confidence": 0.0,
  "needs_admin": false,
  "reason": "سبب قصير"
}}

رسالة الزبون:
{customer_text}

قائمة المنتجات:
{context}
""".strip()


def _success(provider: str, data: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    confidence = data.get("confidence", 0)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0
    if confidence > 1:
        confidence = confidence / 100.0
    return {
        "success": True,
        "provider": provider,
        "product_name": data.get("product_name", "") or data.get("name", ""),
        "matched_id": data.get("matched_id", "") or data.get("id", ""),
        "confidence": confidence,
        "needs_admin": bool(data.get("needs_admin", False)),
        "reason": data.get("reason", ""),
        "raw_text": raw_text[:1000],
    }


def _fail(provider: str, error: Any) -> Dict[str, Any]:
    return {"success": False, "provider": provider, "error": str(error)[:1000]}


def _call_gemini(api_key: str, customer_text: str, products: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    model = os.getenv("GEMINI_TEXT_MODEL", os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash"))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": _prompt(customer_text, products)}]}],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"},
    }
    r = requests.post(url, json=payload, timeout=35)
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


def _call_openrouter(customer_text: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY missing")
    model = os.getenv("OPENROUTER_TEXT_MODEL", os.getenv("OPENROUTER_VISION_MODEL", "qwen/qwen2.5-vl-72b-instruct:free"))
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _prompt(customer_text, products)}],
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://example.com"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "WhatsPriceBot"),
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _json_from_text(str(text))
    if not parsed:
        raise RuntimeError(f"No JSON parsed from OpenRouter response: {str(text)[:600]}")
    return _success("openrouter", parsed, str(text))


def _call_xai(customer_text: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.getenv("XAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("XAI_API_KEY missing")
    model = os.getenv("XAI_TEXT_MODEL", os.getenv("XAI_VISION_MODEL", "grok-4.3"))
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _prompt(customer_text, products)}],
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload, timeout=45)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _json_from_text(str(text))
    if not parsed:
        raise RuntimeError(f"No JSON parsed from xAI response: {str(text)[:600]}")
    return _success("grok", parsed, str(text))


def resolve_product_from_text_ai(customer_text: str, products: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    products = products or []
    order = os.getenv("TEXT_AI_PROVIDER_ORDER", "gemini1,openrouter,grok")
    providers = [x.strip().lower() for x in order.split(",") if x.strip()]
    errors = []
    for provider in providers:
        try:
            if provider == "gemini1":
                key = os.getenv("GEMINI_API_KEY_1", "")
                if not key:
                    errors.append(_fail(provider, "GEMINI_API_KEY_1 missing"))
                    continue
                return _call_gemini(key, customer_text, products, "gemini1")
            if provider == "gemini2":
                key = os.getenv("GEMINI_API_KEY_2", "")
                if not key:
                    errors.append(_fail(provider, "GEMINI_API_KEY_2 missing"))
                    continue
                return _call_gemini(key, customer_text, products, "gemini2")
            if provider == "openrouter":
                return _call_openrouter(customer_text, products)
            if provider in {"grok", "xai"}:
                return _call_xai(customer_text, products)
            errors.append(_fail(provider, "unknown provider"))
        except Exception as e:
            errors.append(_fail(provider, e))
            continue
    return {"success": False, "provider": "none", "error": "all text AI providers failed", "errors": errors}
