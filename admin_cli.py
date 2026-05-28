#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os
from pathlib import Path

PRODUCTS_FILE = Path('products.json')
CONVERSATIONS_FILE = Path('conversations.json')

def read_json(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return default

def products_cmd(args):
    for p in read_json(PRODUCTS_FILE, []):
        print(f"- {p.get('id')} | {p.get('name')} | {p.get('price')} | {p.get('stock')}")

def inbox_cmd(args):
    for c in read_json(CONVERSATIONS_FILE, []):
        if c.get('status') == 'open':
            msg = c.get('messages', [{}])[-1].get('text', '')
            print(f"- {c.get('id')} | {c.get('from')} | {c.get('reason')} | {msg}")

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd')
    sub.add_parser('products').set_defaults(func=products_cmd)
    sub.add_parser('inbox').set_defaults(func=inbox_cmd)
    args = parser.parse_args()
    if not hasattr(args, 'func'):
        parser.print_help(); return
    args.func(args)

if __name__ == '__main__':
    main()
