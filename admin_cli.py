#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
from datetime import datetime

PRODUCTS_FILE = "products.json"
PENDING_FILE = "pending_reviews.json"
ORDERS_FILE = "orders.json"


def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now():
    return datetime.now().isoformat(timespec="seconds")


def products_cmd(args):
    products = read_json(PRODUCTS_FILE, [])
    print("\n=== PRODUCTS ===")
    if not products:
        print("No products found.")
        return

    for p in products:
        aliases = ", ".join(p.get("aliases", []))
        print(f"- {p.get('id')} | {p.get('name')} | {p.get('price')} | {p.get('stock')}")
        if aliases:
            print(f"  aliases: {aliases}")
        if p.get("notes"):
            print(f"  notes: {p.get('notes')}")
    print()


def pending_cmd(args):
    pending = read_json(PENDING_FILE, [])
    print("\n=== PENDING REVIEWS ===")
    if not pending:
        print("No pending reviews.")
        return

    for item in pending:
        print(f"- {item.get('id')} | {item.get('kind')} | {item.get('status')} | from={item.get('from')}")
        print(f"  name: {item.get('name')}")
        print(f"  text: {item.get('text')}")
        if item.get("media_id"):
            print(f"  media_id: {item.get('media_id')}")
    print()


def orders_cmd(args):
    orders = read_json(ORDERS_FILE, [])
    print("\n=== ORDERS ===")
    if not orders:
        print("No orders.")
        return

    for o in orders:
        print(f"- {o.get('id')} | {o.get('status')} | from={o.get('from')} | {o.get('created_at')}")
        print(f"  name: {o.get('name')}")
        print(f"  text: {o.get('text')}")
    print()


def add_product_cmd(args):
    products = read_json(PRODUCTS_FILE, [])
    product_id = args.id.strip()

    aliases = []
    if args.aliases:
        aliases = [x.strip() for x in args.aliases.split(",") if x.strip()]

    new_product = {
        "id": product_id,
        "name": args.name.strip(),
        "price": args.price.strip(),
        "stock": args.stock.strip(),
        "notes": args.notes.strip() if args.notes else "",
        "aliases": aliases,
    }

    replaced = False
    for i, p in enumerate(products):
        if p.get("id") == product_id:
            products[i] = new_product
            replaced = True
            break

    if not replaced:
        products.append(new_product)

    write_json(PRODUCTS_FILE, products)
    print(f"OK: product saved: {product_id}")


def add_alias_cmd(args):
    products = read_json(PRODUCTS_FILE, [])
    target = args.product.strip()
    alias = args.alias.strip()

    for p in products:
        if p.get("id") == target:
            aliases = p.setdefault("aliases", [])
            if alias not in aliases:
                aliases.append(alias)
            write_json(PRODUCTS_FILE, products)
            print(f"OK: alias added to {target}: {alias}")
            return

    print(f"ERROR: product not found: {target}")


def resolve_cmd(args):
    pending = read_json(PENDING_FILE, [])
    products = read_json(PRODUCTS_FILE, [])

    pending_id = args.pending.strip()
    product_id = args.product.strip()
    alias = args.alias.strip() if args.alias else ""

    found_pending = None
    for item in pending:
        if item.get("id") == pending_id:
            found_pending = item
            break

    if not found_pending:
        print(f"ERROR: pending not found: {pending_id}")
        return

    found_product = None
    for p in products:
        if p.get("id") == product_id:
            found_product = p
            break

    if not found_product:
        print(f"ERROR: product not found: {product_id}")
        return

    if not alias:
        alias = found_pending.get("text", "").strip()

    if alias:
        aliases = found_product.setdefault("aliases", [])
        if alias not in aliases:
            aliases.append(alias)

    found_pending["status"] = "resolved"
    found_pending["resolved_at"] = now()
    found_pending["resolved_product_id"] = product_id
    found_pending["resolved_alias"] = alias

    write_json(PRODUCTS_FILE, products)
    write_json(PENDING_FILE, pending)

    print(f"OK: pending {pending_id} resolved to {product_id}")
    if alias:
        print(f"OK: alias learned: {alias}")


def main():
    parser = argparse.ArgumentParser(description="WhatsPriceBot Admin CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("products").set_defaults(func=products_cmd)
    sub.add_parser("pending").set_defaults(func=pending_cmd)
    sub.add_parser("orders").set_defaults(func=orders_cmd)

    p_add = sub.add_parser("add")
    p_add.add_argument("--id", required=True)
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--price", required=True)
    p_add.add_argument("--stock", default="متوفر")
    p_add.add_argument("--notes", default="")
    p_add.add_argument("--aliases", default="")
    p_add.set_defaults(func=add_product_cmd)

    p_alias = sub.add_parser("alias")
    p_alias.add_argument("--product", required=True)
    p_alias.add_argument("--alias", required=True)
    p_alias.set_defaults(func=add_alias_cmd)

    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("--pending", required=True)
    p_resolve.add_argument("--product", required=True)
    p_resolve.add_argument("--alias", default="")
    p_resolve.set_defaults(func=resolve_cmd)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
