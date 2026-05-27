#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os
from datetime import datetime
PRODUCTS_FILE='products.json'; PENDING_FILE='pending_reviews.json'; ORDERS_FILE='orders.json'
def read_json(p,d):
    if not os.path.exists(p): return d
    try: return json.load(open(p,encoding='utf-8'))
    except Exception: return d
def write_json(p,d): json.dump(d, open(p,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
def products_cmd(args):
    for p in read_json(PRODUCTS_FILE,[]): print(f"- {p.get('id')} | {p.get('category','')} | {p.get('name')} | {p.get('price')} | {p.get('stock')}\n  aliases: {', '.join(p.get('aliases',[]))}")
def pending_cmd(args):
    for x in read_json(PENDING_FILE,[]): print(f"- {x.get('id')} | {x.get('kind')} | {x.get('status')} | {x.get('text')} | vision={(x.get('vision_result') or {}).get('product_name','')}")
def orders_cmd(args):
    for o in read_json(ORDERS_FILE,[]): print(f"- {o.get('id')} | {o.get('status')} | {o.get('from')} | {o.get('text')}")
def add_cmd(args):
    ps=read_json(PRODUCTS_FILE,[]); aliases=[x.strip() for x in args.aliases.split(',') if x.strip()]
    item={'id':args.id,'category':args.category,'name':args.name,'price':args.price,'stock':args.stock,'quantity':args.quantity,'expiry_date':args.expiry_date,'notes':args.notes,'aliases':aliases}
    for i,p in enumerate(ps):
        if p.get('id')==args.id: ps[i]=item; write_json(PRODUCTS_FILE,ps); print('OK'); return
    ps.append(item); write_json(PRODUCTS_FILE,ps); print('OK')
def alias_cmd(args):
    ps=read_json(PRODUCTS_FILE,[])
    for p in ps:
        if p.get('id')==args.product:
            if args.alias not in p.setdefault('aliases',[]): p['aliases'].append(args.alias)
            write_json(PRODUCTS_FILE,ps); print('OK'); return
    print('ERROR product not found')
def resolve_cmd(args):
    pend=read_json(PENDING_FILE,[]); ps=read_json(PRODUCTS_FILE,[])
    it=next((x for x in pend if x.get('id')==args.pending),None); p=next((x for x in ps if x.get('id')==args.product),None)
    if not it or not p: print('ERROR not found'); return
    alias=args.alias or it.get('text') or (it.get('vision_result') or {}).get('product_name','')
    if alias and alias not in p.setdefault('aliases',[]): p['aliases'].append(alias)
    it.update({'status':'resolved','resolved_at':datetime.now().isoformat(timespec='seconds'),'resolved_product_id':args.product,'resolved_alias':alias})
    write_json(PRODUCTS_FILE,ps); write_json(PENDING_FILE,pend); print('OK')
def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='cmd')
    sub.add_parser('products').set_defaults(func=products_cmd); sub.add_parser('pending').set_defaults(func=pending_cmd); sub.add_parser('orders').set_defaults(func=orders_cmd)
    p=sub.add_parser('add'); p.add_argument('--id',required=True); p.add_argument('--category',default=''); p.add_argument('--name',required=True); p.add_argument('--price',required=True); p.add_argument('--stock',default='متوفر'); p.add_argument('--quantity',default=''); p.add_argument('--expiry-date',default=''); p.add_argument('--notes',default=''); p.add_argument('--aliases',default=''); p.set_defaults(func=add_cmd)
    p=sub.add_parser('alias'); p.add_argument('--product',required=True); p.add_argument('--alias',required=True); p.set_defaults(func=alias_cmd)
    p=sub.add_parser('resolve'); p.add_argument('--pending',required=True); p.add_argument('--product',required=True); p.add_argument('--alias',default=''); p.set_defaults(func=resolve_cmd)
    args=parser.parse_args(); getattr(args,'func',lambda a: parser.print_help())(args)
if __name__=='__main__': main()
