#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

def send_text(body):
    data = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "local_test",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "contacts": [{"profile": {"name": "Local Test User"}, "wa_id": "218934037986"}],
                    "messages": [{
                        "id": "test-" + body.replace(" ", "-"),
                        "from": "218934037986",
                        "type": "text",
                        "text": {"body": body}
                    }]
                }
            }]
        }]
    }
    r = requests.post("http://127.0.0.1:8090/webhook", json=data, timeout=20)
    print(body, "=>", r.status_code, r.text)

send_text("panadol")
send_text("عندكم اوجمنتين؟")
send_text("iphone 15 pro")
send_text("سامسونق الترا")
send_text("عندكم منتج غريب")
send_text("نبي نطلب")
