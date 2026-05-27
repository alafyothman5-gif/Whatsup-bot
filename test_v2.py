#!/usr/bin/env python3
import requests
def send_text(body):
    data={"object":"whatsapp_business_account","entry":[{"id":"local_test","changes":[{"field":"messages","value":{"messaging_product":"whatsapp","contacts":[{"profile":{"name":"Local Test User"},"wa_id":"218934037986"}],"messages":[{"id":"test-"+body.replace(" ","-"),"from":"218934037986","type":"text","text":{"body":body}}]}}]}]}
    r=requests.post("http://127.0.0.1:8090/webhook",json=data,timeout=20); print(body, "=>", r.status_code, r.text)
for x in ["panadol","عندكم اوجمنتين؟","iphone 15 pro","سامسونق الترا","عندكم منتج غريب","نبي نطلب"]: send_text(x)
