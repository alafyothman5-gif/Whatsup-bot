#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

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
                    "id": "image-test-1",
                    "from": "218934037986",
                    "type": "image",
                    "image": {
                        "id": "fake_media_id_for_local_test",
                        "caption": "صورة panadol"
                    }
                }]
            }
        }]
    }]
}

r = requests.post("http://127.0.0.1:8090/webhook", json=data, timeout=20)
print(r.status_code, r.text)
