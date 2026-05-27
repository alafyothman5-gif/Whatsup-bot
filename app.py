#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, redirect
import datetime, json, os, re, uuid, requests
from difflib import SequenceMatcher
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from vision import analyze_image_with_fallback

app = Flask(__name__)
VERIFY_TOKEN=os.getenv("VERIFY_TOKEN","WhatsPrice2026")
PHONE_NUMBER_ID=os.getenv("PHONE_NUMBER_ID","")
WHATSAPP_TOKEN=os.getenv("WHATSAPP_TOKEN","")
ADMIN_TOKEN=os.getenv("ADMIN_TOKEN","admin2026")
VISION_ENABLED=os.getenv("VISION_ENABLED","true").lower() in ("1","true","yes","on")
PRODUCTS_FILE="products.json"; WEBHOOK_LOG="webhook_log.txt"; SEND_LOG="send_log.txt"; PENDING_FILE="pending_reviews.json"; ORDERS_FILE="orders.json"; VISION_LOG="vision_log.txt"; MEDIA_DIR="media"
os.makedirs(MEDIA_DIR, exist_ok=True)

def now(): return datetime.datetime.now().isoformat(timespec="seconds")
def read_json(p,d):
    try:
        if not os.path.exists(p): return d
        return json.load(open(p,encoding="utf-8"))
    except Exception: return d
def write_json(p,data):
    tmp=p+".tmp"
    json.dump(data, open(tmp,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    os.replace(tmp,p)
def log(p,t): open(p,"a",encoding="utf-8").write(t+"\n")
def norm(t):
    t=(t or "").lower().strip()
    for a,b in {"أ":"ا","إ":"ا","آ":"ا","ى":"ي","ة":"ه","ؤ":"و","ئ":"ي","گ":"ق"}.items(): t=t.replace(a,b)
    for a,b in {"سامسونق":"سامسونج","سمسونج":"سامسونج","ايفون":"iphone","آيفون":"iphone","ايربودز":"airpods","اير بودز":"airpods","برو ماكس":"pro max","برو":"pro","الترا":"ultra"}.items(): t=t.replace(a,b)
    for w in ["عندكم","عندك","في","فيه","متوفر","متوفره","متوفرة","بكم","كم","سعر","شن","شنو","لو","موجود","نبي","ابي","هذا","هدا","هذه","الصورة","صورة"]:
        t=re.sub(rf"\b{re.escape(w)}\b"," ",t)
    return re.sub(r"\s+"," ",re.sub(r"[^\w\s\u0600-\u06FF]"," ",t)).strip()

def ensure_products():
    if os.path.exists(PRODUCTS_FILE): return
    write_json(PRODUCTS_FILE, [
        {"id":"panadol_500","category":"مسكنات","name":"Panadol 500mg","price":"12 د.ل","stock":"متوفر","quantity":"20","expiry_date":"2027-05","notes":"للاستخدام والجرعة يرجى سؤال الصيدلي.","aliases":["panadol","بندول","بانادول","paracetamol","باراسيتامول"]},
        {"id":"augmentin_1g","category":"مضادات حيوية","name":"Augmentin 1g","price":"35 د.ل","stock":"متوفر","quantity":"10","expiry_date":"2026-12","notes":"يصرف حسب إرشاد الطبيب أو الصيدلي.","aliases":["augmentin","اوجمنتين","اموكسكلاف","amoxiclav"]},
        {"id":"iphone_15_pro","category":"هواتف","name":"iPhone 15 Pro","price":"5200 د.ل","stock":"متوفر","quantity":"3","expiry_date":"","notes":"السعر قابل للتغيير حسب اللون والسعة","aliases":["iphone 15 pro","15 pro","ايفون 15 برو","iphone برو","ايفون برو"]},
        {"id":"s24_ultra","category":"هواتف","name":"Samsung S24 Ultra","price":"5400 د.ل","stock":"متوفر","quantity":"2","expiry_date":"","notes":"متوفر حسب السعة واللون","aliases":["s24 ultra","s24","سامسونج s24","سامسونق s24","اس 24 الترا","سامسونق الترا"]}
    ])
def products(): ensure_products(); return read_json(PRODUCTS_FILE,[])
def save_products(x): write_json(PRODUCTS_FILE,x)
def sim(a,b): return SequenceMatcher(None,a,b).ratio()
def find_product(text):
    clean=norm(text)
    if not clean: return None,0,""
    for p in products():
        for c0 in [p.get("name","")]+p.get("aliases",[]):
            c=norm(c0)
            if c and (c==clean or c in clean or clean in c): return p,1,c0
    cw=set(clean.split()); best=None; bs=0; ba=""
    for p in products():
        for c0 in [p.get("name","")]+p.get("aliases",[]):
            c=norm(c0); words=set(c.split())
            if not words: continue
            score=max(len(cw & words)/max(len(words),1), sim(clean,c))
            if score>bs: best=p; bs=score; ba=c0
    return (best,bs,ba) if bs>=0.75 else (None,bs,ba)
def product_reply(p):
    msg=(f"المنتج: {p.get('name')}\nالسعر: {p.get('price')}\nالحالة: {p.get('stock')} ❌" if "غير" in p.get("stock","") else f"نعم متوفر ✅\nالمنتج: {p.get('name')}\nالسعر: {p.get('price')}\nالحالة: {p.get('stock')}")
    for label,key in [("القسم","category"),("الكمية","quantity"),("تاريخ الانتهاء","expiry_date"),("ملاحظة","notes")]:
        if p.get(key): msg += f"\n{label}: {p.get(key)}"
    return msg+"\n\nلو تبي نجهز لك الطلب، اكتب: نبي نطلب"
def save_pending(kind,sender,name,text="",raw=None,media_id="",vision_result=None):
    arr=read_json(PENDING_FILE,[]); item={"id":str(uuid.uuid4())[:8],"created_at":now(),"kind":kind,"from":sender,"name":name,"text":text,"media_id":media_id,"status":"open","vision_result":vision_result or {}, "raw":raw or {}}
    arr.append(item); write_json(PENDING_FILE,arr); return item
def save_order(sender,name,text):
    arr=read_json(ORDERS_FILE,[]); item={"id":str(uuid.uuid4())[:8],"created_at":now(),"from":sender,"name":name,"text":text,"status":"new"}; arr.append(item); write_json(ORDERS_FILE,arr); return item
def send_text(to,body):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        log(SEND_LOG,f"{now()} | NO_TOKEN_OR_PHONE_ID | to={to} | BODY={body}"); return False,"NO_TOKEN_OR_PHONE_ID"
    r=requests.post(f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization":f"Bearer {WHATSAPP_TOKEN}","Content-Type":"application/json"}, json={"messaging_product":"whatsapp","to":to,"type":"text","text":{"preview_url":False,"body":body}}, timeout=20)
    log(SEND_LOG,f"{now()} | STATUS={r.status_code} | BODY={body} | RESPONSE={r.text}"); return r.status_code<300,r.text
def download_media(media_id):
    if not media_id or not WHATSAPP_TOKEN: return None,"","NO_MEDIA_ID_OR_TOKEN"
    h={"Authorization":f"Bearer {WHATSAPP_TOKEN}"}
    r=requests.get(f"https://graph.facebook.com/v25.0/{media_id}",headers=h,timeout=20)
    if r.status_code>=300: return None,"",f"META_MEDIA_INFO_ERROR {r.status_code}: {r.text}"
    info=r.json(); url=info.get("url"); mime=info.get("mime_type","image/jpeg")
    if not url: return None,"","NO_MEDIA_URL"
    m=requests.get(url,headers=h,timeout=30)
    if m.status_code>=300: return None,"",f"META_MEDIA_DOWNLOAD_ERROR {m.status_code}: {m.text}"
    return m.content,mime,""
def extract(data):
    out=[]
    for e in data.get("entry",[]):
        for ch in e.get("changes",[]):
            v=ch.get("value",{}); contacts=v.get("contacts",[]); name=contacts[0].get("profile",{}).get("name","") if contacts else ""
            for msg in v.get("messages",[]):
                typ=msg.get("type",""); text=""; media=""
                if typ=="text": text=msg.get("text",{}).get("body","")
                elif typ=="image": media=msg.get("image",{}).get("id",""); text=msg.get("image",{}).get("caption","")
                out.append({"from":msg.get("from",""),"name":name,"type":typ,"text":text,"media_id":media,"raw":msg})
    return out
def handle_text(sender,name,text):
    clean=norm(text)
    if any(norm(w) in clean for w in ["نبي نطلب","نبي طلب","نطلب","نبيه","ناخده","نبي ناخد","احجز","اطلب"]):
        o=save_order(sender,name,text); send_text(sender,f"تم تسجيل طلبك ✅\nرقم الطلب: {o['id']}\nسيتم التواصل معك من الموظف للتأكيد."); return
    p,_,_=find_product(text)
    if p: send_text(sender,product_reply(p)); return
    pe=save_pending("unknown_text",sender,name,text=text); send_text(sender,f"وصلت رسالتك ✅\nلم أتعرف على المنتج بدقة.\nسيتم تحويلها للموظف للمراجعة.\nرقم المراجعة: {pe['id']}")
def handle_image(sender,name,text,media_id,raw):
    if not VISION_ENABLED:
        pe=save_pending("image",sender,name,text=text,media_id=media_id,raw=raw); send_text(sender,f"وصلت الصورة ✅\nسيتم التحقق من المنتج والرد عليك بالسعر والتوفر.\nرقم المراجعة: {pe['id']}"); return
    img,mime,err=download_media(media_id)
    if not img:
        vr={"success":False,"error":err}; pe=save_pending("image_media_download_failed",sender,name,text=text,media_id=media_id,raw=raw,vision_result=vr); send_text(sender,f"وصلت الصورة ✅\nلم أتمكن من قراءتها الآن وسيتم تحويلها للموظف.\nرقم المراجعة: {pe['id']}"); return
    vr=analyze_image_with_fallback(img,mime,text,products()); log(VISION_LOG,f"{now()} | {json.dumps(vr,ensure_ascii=False)}")
    guess=" ".join([text or "", str(vr.get("product_name","")), str(vr.get("brand","")), str(vr.get("visible_text","")), str(vr.get("generic_name",""))])
    p,_,_=find_product(guess)
    if vr.get("success") and p:
        send_text(sender,product_reply(p)+"\n\nتم التعرف على الصورة تلقائيًا ✅"); return
    pe=save_pending("image_needs_review",sender,name,text=text,media_id=media_id,raw=raw,vision_result=vr)
    msg=f"وصلت الصورة ✅\nلم أتعرف على المنتج بدقة كافية.\nسيتم تحويلها للموظف للمراجعة.\nرقم المراجعة: {pe['id']}"
    if vr.get("product_name"): msg += f"\nتوقع مبدئي: {vr.get('product_name')}"
    send_text(sender,msg)
def esc(x): return str(x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def admin_allowed(): return request.args.get("token")==ADMIN_TOKEN
def admin_url(path="/admin"): return f"{path}?token={ADMIN_TOKEN}"

@app.get("/")
def home(): return jsonify({"status":"running","name":"WhatsPriceBot Vision","time":now(),"meta_ready":bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID),"vision_enabled":VISION_ENABLED})
@app.get("/health")
def health(): return jsonify({"ok":True,"products":len(products()),"pending":len(read_json(PENDING_FILE,[])),"orders":len(read_json(ORDERS_FILE,[])),"token_loaded":bool(WHATSAPP_TOKEN),"phone_number_id_loaded":bool(PHONE_NUMBER_ID),"vision_enabled":VISION_ENABLED})
@app.get("/admin")
def admin():
    if not admin_allowed(): return "Forbidden",403
    ps=products(); pend=read_json(PENDING_FILE,[]); orders=read_json(ORDERS_FILE,[])
    ph="".join(f"<tr><td>{esc(p.get('id'))}</td><td>{esc(p.get('category'))}</td><td>{esc(p.get('name'))}</td><td>{esc(p.get('price'))}</td><td>{esc(p.get('stock'))}</td><td>{esc(p.get('quantity'))}</td><td>{esc(p.get('expiry_date'))}</td><td>{esc(', '.join(p.get('aliases',[])))}</td></tr>" for p in ps)
    penh=""
    for it in pend:
        vr=it.get("vision_result") or {}; form=""
        if it.get("status")=="open":
            form=f"<form method='post' action='/admin/resolve?token={esc(ADMIN_TOKEN)}'><input type='hidden' name='pending_id' value='{esc(it.get('id'))}'><input name='product_id' placeholder='product_id'><input name='alias' placeholder='alias اختياري'><button>ربط</button></form>"
        penh += f"<tr><td>{esc(it.get('id'))}</td><td>{esc(it.get('kind'))}</td><td>{esc(it.get('status'))}</td><td>{esc(it.get('from'))}</td><td>{esc(it.get('text'))}</td><td>{esc(vr.get('provider'))}</td><td>{esc(vr.get('product_name'))}</td><td>{form}</td></tr>"
    oh="".join(f"<tr><td>{esc(o.get('id'))}</td><td>{esc(o.get('status'))}</td><td>{esc(o.get('from'))}</td><td>{esc(o.get('text'))}</td><td>{esc(o.get('created_at'))}</td></tr>" for o in orders)
    return f"""<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>WhatsPriceBot Admin</title><style>body{{font-family:Arial;background:#f5f5f5;padding:20px}}.card{{background:white;padding:16px;margin-bottom:16px;border-radius:12px;box-shadow:0 2px 8px #0001;overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:right;vertical-align:top}}th{{background:#eee}}input{{padding:8px;margin:4px;border:1px solid #ccc;border-radius:8px}}button{{padding:8px 12px;margin:4px;border:0;border-radius:8px;background:#128c7e;color:white}}</style>
    <h1>WhatsPriceBot Admin</h1><div class='card'><h2>الحالة</h2><p>البوت شغال ✅</p><p>Products: {len(ps)} | Pending: {len(pend)} | Orders: {len(orders)} | Vision: {VISION_ENABLED}</p></div>
    <div class='card'><h2>إضافة منتج</h2><form method='post' action='/admin/add_product?token={esc(ADMIN_TOKEN)}'><input name='id' placeholder='id' required><input name='category' placeholder='القسم'><input name='name' placeholder='اسم المنتج' required><input name='price' placeholder='السعر' required><input name='stock' value='متوفر'><input name='quantity' placeholder='الكمية'><input name='expiry_date' placeholder='تاريخ الانتهاء'><input name='notes' placeholder='ملاحظة'><input name='aliases' placeholder='aliases بفواصل'><button>حفظ</button></form></div>
    <div class='card'><h2>إضافة Alias</h2><form method='post' action='/admin/add_alias?token={esc(ADMIN_TOKEN)}'><input name='product_id' placeholder='product_id' required><input name='alias' placeholder='alias' required><button>إضافة</button></form></div>
    <div class='card'><h2>المنتجات</h2><table><tr><th>ID</th><th>القسم</th><th>الاسم</th><th>السعر</th><th>التوفر</th><th>الكمية</th><th>الصلاحية</th><th>Aliases</th></tr>{ph}</table></div>
    <div class='card'><h2>المراجعات</h2><table><tr><th>ID</th><th>النوع</th><th>الحالة</th><th>الرقم</th><th>النص</th><th>Vision</th><th>توقع</th><th>ربط</th></tr>{penh}</table></div>
    <div class='card'><h2>الطلبات</h2><table><tr><th>ID</th><th>الحالة</th><th>الرقم</th><th>النص</th><th>الوقت</th></tr>{oh}</table></div></html>"""
@app.post("/admin/add_product")
def admin_add_product():
    if not admin_allowed(): return "Forbidden",403
    ps=products(); pid=request.form.get("id","").strip(); aliases=[x.strip() for x in request.form.get("aliases","").split(",") if x.strip()]
    item={"id":pid,"category":request.form.get("category","").strip(),"name":request.form.get("name","").strip(),"price":request.form.get("price","").strip(),"stock":request.form.get("stock","متوفر").strip(),"quantity":request.form.get("quantity","").strip(),"expiry_date":request.form.get("expiry_date","").strip(),"notes":request.form.get("notes","").strip(),"aliases":aliases}
    for i,p in enumerate(ps):
        if p.get("id")==pid:
            for a in p.get("aliases",[]):
                if a not in item["aliases"]: item["aliases"].append(a)
            ps[i]=item; save_products(ps); return redirect(admin_url())
    ps.append(item); save_products(ps); return redirect(admin_url())
@app.post("/admin/add_alias")
def admin_alias():
    if not admin_allowed(): return "Forbidden",403
    pid=request.form.get("product_id","").strip(); alias=request.form.get("alias","").strip(); ps=products()
    for p in ps:
        if p.get("id")==pid:
            if alias and alias not in p.setdefault("aliases",[]): p["aliases"].append(alias)
            save_products(ps); return redirect(admin_url())
    return "Product not found",404
@app.post("/admin/resolve")
def admin_resolve():
    if not admin_allowed(): return "Forbidden",403
    pending=read_json(PENDING_FILE,[]); ps=products(); pending_id=request.form.get("pending_id","").strip(); pid=request.form.get("product_id","").strip(); alias=request.form.get("alias","").strip()
    item=next((x for x in pending if x.get("id")==pending_id),None); p=next((x for x in ps if x.get("id")==pid),None)
    if not item or not p: return "Not found",404
    if not alias: alias=item.get("text","").strip() or (item.get("vision_result") or {}).get("product_name","")
    if alias and alias not in p.setdefault("aliases",[]): p["aliases"].append(alias)
    item.update({"status":"resolved","resolved_at":now(),"resolved_product_id":pid,"resolved_alias":alias})
    write_json(PENDING_FILE,pending); save_products(ps)
    if item.get("from"): send_text(item["from"], product_reply(p))
    return redirect(admin_url())
@app.get("/webhook")
def verify():
    if request.args.get("hub.mode")=="subscribe" and request.args.get("hub.verify_token")==VERIFY_TOKEN:
        return request.args.get("hub.challenge",""),200
    return "Verification failed",403
@app.post("/webhook")
def receive():
    data=request.get_json(silent=True) or {}; log(WEBHOOK_LOG,"\n--- NEW WEBHOOK ---"); log(WEBHOOK_LOG,now()); log(WEBHOOK_LOG,json.dumps(data,ensure_ascii=False,indent=2))
    for msg in extract(data):
        if msg["type"]=="text": handle_text(msg["from"],msg["name"],msg["text"])
        elif msg["type"]=="image": handle_image(msg["from"],msg["name"],msg["text"],msg["media_id"],msg["raw"])
        else:
            pe=save_pending("unsupported",msg["from"],msg["name"],raw=msg["raw"]); send_text(msg["from"],f"وصلت رسالتك ✅\nحاليًا أقدر أتعامل مع النصوص والصور فقط.\nرقم المراجعة: {pe['id']}")
    return jsonify({"status":"received"}),200

if __name__=="__main__":
    ensure_products(); app.run(host="0.0.0.0", port=int(os.getenv("PORT","8090")))
