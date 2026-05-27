#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64, json, os, re, requests

def _parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```json\s*|^```\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
    return {}

def _context(products):
    limit = int(os.getenv("VISION_INCLUDE_PRODUCTS_LIMIT", "80"))
    if limit <= 0:
        return ""
    lines = []
    for p in (products or [])[:limit]:
        lines.append(f"- {p.get('name','')} | aliases: {', '.join(p.get('aliases', [])[:6])}")
    return "منتجات محتملة من قاعدة البيانات:\n" + "\n".join(lines) if lines else ""

def _prompt(caption, products):
    return f"""أنت مساعد يتعرف على منتج من صورة واتساب.
استخرج اسم المنتج فقط. لو دواء، استخرج الاسم التجاري أو العلمي إن ظهر.
لا تعط جرعة ولا نصيحة طبية. لا تخترع سعر أو توفر.
أعد JSON فقط:
{{"product_name":"","brand":"","generic_name":"","visible_text":"","confidence":0.0,"notes":""}}

تعليق العميل: {caption or ""}
{_context(products)}
""".strip()

def _ok(provider, data, raw=""):
    return {
        "success": True,
        "provider": provider,
        "product_name": data.get("product_name","") or data.get("name",""),
        "brand": data.get("brand",""),
        "generic_name": data.get("generic_name",""),
        "visible_text": data.get("visible_text",""),
        "confidence": data.get("confidence",0),
        "notes": data.get("notes",""),
        "raw_text": str(raw)[:1000],
    }

def _call_gemini(key, img, mime, caption, products, label):
    model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [
            {"text": _prompt(caption, products)},
            {"inline_data": {"mime_type": mime or "image/jpeg", "data": base64.b64encode(img).decode()}}
        ]}],
        "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"}
    }
    r = requests.post(url, json=payload, timeout=45)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    text = r.json().get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text","")
    parsed = _parse_json(text)
    if not parsed:
        raise RuntimeError(f"No JSON: {text[:600]}")
    return _ok(label, parsed, text)

def _call_openrouter(img, mime, caption, products):
    key = os.getenv("OPENROUTER_API_KEY","")
    model = os.getenv("OPENROUTER_VISION_MODEL","qwen/qwen2.5-vl-72b-instruct:free")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY missing")
    data_url = f"data:{mime or 'image/jpeg'};base64,{base64.b64encode(img).decode()}"
    payload = {
        "model": model,
        "messages": [{"role":"user","content":[
            {"type":"text","text":_prompt(caption, products)},
            {"type":"image_url","image_url":{"url":data_url}}
        ]}],
        "temperature": 0.1
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL","https://example.com"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME","WhatsPriceBot")
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    text = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
    if isinstance(text, list):
        text = " ".join(map(str,text))
    parsed = _parse_json(str(text))
    if not parsed:
        raise RuntimeError(f"No JSON: {str(text)[:600]}")
    return _ok("openrouter", parsed, text)

def _call_cloudflare(img, mime, caption, products):
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID","")
    token = os.getenv("CLOUDFLARE_API_TOKEN","")
    model = os.getenv("CLOUDFLARE_VISION_MODEL","@cf/meta/llama-3.2-11b-vision-instruct")
    if not account or not token:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN missing")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    payload = {"messages":[{"role":"system","content":"Return JSON only."},{"role":"user","content":_prompt(caption,products)}], "image": base64.b64encode(img).decode()}
    r = requests.post(url, headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"}, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    result = r.json().get("result", {})
    text = result.get("response") or result.get("text") or json.dumps(result, ensure_ascii=False)
    parsed = _parse_json(text)
    if not parsed:
        raise RuntimeError(f"No JSON: {text[:600]}")
    return _ok("cloudflare", parsed, text)

def _call_xai(img, mime, caption, products):
    key = os.getenv("XAI_API_KEY","")
    model = os.getenv("XAI_VISION_MODEL","grok-4.3")
    if not key:
        raise RuntimeError("XAI_API_KEY missing")
    data_url = f"data:{mime or 'image/jpeg'};base64,{base64.b64encode(img).decode()}"
    payload = {"model":model,"messages":[{"role":"user","content":[
        {"type":"text","text":_prompt(caption,products)},
        {"type":"image_url","image_url":{"url":data_url}}
    ]}],"temperature":0.1}
    r = requests.post("https://api.x.ai/v1/chat/completions", headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:600]}")
    text = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
    parsed = _parse_json(str(text))
    if not parsed:
        raise RuntimeError(f"No JSON: {str(text)[:600]}")
    return _ok("grok", parsed, text)

def analyze_image_with_fallback(image_bytes, mime_type, caption="", products=None):
    products = products or []
    order = os.getenv("VISION_PROVIDER_ORDER","gemini1,gemini2,openrouter,cloudflare,grok")
    errors = []
    for provider in [x.strip().lower() for x in order.split(",") if x.strip()]:
        try:
            if provider == "gemini1":
                key = os.getenv("GEMINI_API_KEY_1","")
                if not key: raise RuntimeError("GEMINI_API_KEY_1 missing")
                return _call_gemini(key, image_bytes, mime_type, caption, products, "gemini1")
            if provider == "gemini2":
                key = os.getenv("GEMINI_API_KEY_2","")
                if not key: raise RuntimeError("GEMINI_API_KEY_2 missing")
                return _call_gemini(key, image_bytes, mime_type, caption, products, "gemini2")
            if provider == "openrouter":
                return _call_openrouter(image_bytes, mime_type, caption, products)
            if provider == "cloudflare":
                return _call_cloudflare(image_bytes, mime_type, caption, products)
            if provider in ("grok","xai"):
                return _call_xai(image_bytes, mime_type, caption, products)
            raise RuntimeError("unknown provider")
        except Exception as e:
            errors.append({"provider": provider, "error": str(e)[:1000]})
    return {"success": False, "provider": "none", "error": "all vision providers failed", "errors": errors}
