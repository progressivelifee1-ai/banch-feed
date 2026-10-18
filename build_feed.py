#!/usr/bin/env python3
"""Собирает Google Merchant фид banch.com.ua.
base.json  - основа: все товары (скрытые идут как out of stock).
Публичный API Tilda - видимые товары (актуальные цена/наличие, новые товары).
"""
import json, os, sys, time, urllib.request, urllib.parse
from xml.sax.saxutils import escape

API = "https://store.tildaapi.one/api/getproductslist/"
PARAMS = {"storepartuid": "295655874311", "recid": "273261007", "getparts": "true",
          "getoptions": "true", "flag_root": "withroot", "size": "100"}
SHIP = "50 UAH"
LABEL = "От 150 до 250"


def fetch_visible():
    out, slice_ = [], 1
    while True:
        q = dict(PARAMS, slice=str(slice_), c=str(int(time.time() * 1000)))
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q),
                                     headers={"User-Agent": "Mozilla/5.0"})
        data = json.load(urllib.request.urlopen(req, timeout=60))
        prods = data.get("products") or []
        out += prods
        if not prods or len(out) >= int(data.get("total") or 0):
            return out
        slice_ += 1


def money(v):
    f = float(v)
    return str(int(f)) if f == int(f) else "%.2f" % f


def imgs_of(p):
    try:
        g = json.loads(p.get("gallery") or "[]")
    except ValueError:
        return []
    return [x["img"] for x in g if isinstance(x, dict) and x.get("img")]


def item(sku, title, desc, link, imgs, avail, price):
    s = ["<item>", "<g:id>%s</g:id>" % escape(sku), "<g:title>%s</g:title>" % escape(title),
         "<g:description>%s</g:description>" % escape(desc or title),
         "<g:link>%s</g:link>" % escape(link)]
    if imgs:
        s.append("<g:image_link>%s</g:image_link>" % escape(imgs[0]))
        s += ["<g:additional_image_link>%s</g:additional_image_link>" % escape(i) for i in imgs[1:10]]
    s += ["<g:condition>new</g:condition>", "<g:availability>%s</g:availability>" % avail,
          "<g:price>%s UAH</g:price>" % price,
          "<g:custom_label_0>%s</g:custom_label_0>" % LABEL,
          "<g:shipping>", "<g:country>UA</g:country>", "<g:service>Standard</g:service>",
          "<g:price>%s</g:price>" % SHIP, "</g:shipping>", "</item>"]
    return "\n".join(s)


def build(base, visible):
    vis = {str(p.get("sku", "")).strip(): p for p in visible if str(p.get("sku", "")).strip()}
    items, seen = [], set()
    for b in base:
        sku = b["sku"]
        seen.add(sku)
        v = vis.get(sku)
        if v:
            q = str(v.get("quantity", "")).strip()
            avail = "out of stock" if q == "0" else "in stock"
            price = money(v["price"])
            title = v.get("title") or b["title"]
            link = v.get("url") or b["link"]
            imgs = b["imgs"] or imgs_of(v)
        else:
            avail, price, title, link, imgs = "out of stock", b["price"], b["title"], b["link"], b["imgs"]
        items.append(item(sku, title, b["desc"], link, imgs, avail, price))
    for sku, v in vis.items():  # новые товары, которых нет в основе
        if sku in seen:
            continue
        q = str(v.get("quantity", "")).strip()
        items.append(item(sku, v["title"], v.get("descr") or v.get("text") or "", v.get("url") or "",
                          imgs_of(v), "out of stock" if q == "0" else "in stock", money(v["price"])))
    head = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">\n<channel>\n'
            '<title>Banch</title>\n<link>https://banch.com.ua</link>\n'
            '<description>Banch - интернет-магазин</description>\n')
    return head + "\n".join(items) + "\n</channel>\n</rss>\n", len(items)


if __name__ == "__main__":
    base = json.load(open("base.json", encoding="utf-8"))
    vis = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else fetch_visible()
    if len(vis) == 0:
        sys.exit("API вернул 0 товаров - фид не обновляю")
    xml, n = build(base, vis)
    os.makedirs("docs", exist_ok=True)
    open("docs/feed.xml", "w", encoding="utf-8").write(xml)
    print("items:", n, "visible from API:", len(vis))
