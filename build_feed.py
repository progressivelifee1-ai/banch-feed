#!/usr/bin/env python3
"""Собирает Google Merchant фид banch.com.ua.
base.json  - основа: все товары (скрытые идут как out of stock).
Публичный API Tilda - видимые товары (актуальные цена/наличие, новые товары).
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from html.parser import HTMLParser
from xml.sax.saxutils import escape

API = "https://store.tildaapi.one/api/getproductslist/"
PARAMS = {"storepartuid": "295655874311", "recid": "273261007", "getparts": "true",
          "getoptions": "true", "flag_root": "withroot", "size": "100"}
SHIP = "50 UAH"
LABEL = "От 150 до 250"
SHOP_DESC = "banch.com.ua - интернет-магазин популярных товаров по доступным ценам с доставкой по Украине. Товары для дома и кухни, сад и огород, охота и рыбалка, автотовары, уход за собой, гаджеты и электроника. Отправка в течение 1 рабочего дня, оплата при получении."
FETCH_PAGES = True  # описание и фото ВСЕХ товаров брать со страниц сайта (скрытые тоже)


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


VOID = {"br", "img", "hr", "input", "meta", "link", "area", "base", "col", "embed", "source", "wbr"}


class PageParser(HTMLParser):
    """Со страницы товара достаёт описание и фото:
    - .t762__descr (короткое описание у кнопки купить, берём один раз);
    - текстовые блоки ниже (записи Tilda тип 60 - заголовки, 61 - текст):
      "Описание:", "Особенности:", "Характеристики:", "Комплектация:" и т.д.;
    - фото .t-slds__bgimg."""

    BLOCKS = ("60", "61")
    NL = ("br", "li", "p", "ul", "ol", "div")

    def __init__(self):
        super().__init__()
        self.imgs, self.parts = [], []
        self._d, self._done, self._rt, self._skip = 0, False, "", 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if a.get("data-record-type") is not None:
            self._rt = a["data-record-type"]
        if tag in ("style", "script"):
            self._skip += 1
        if tag in VOID:
            pass
        elif self._d:
            self._d += 1
        elif "t762__descr" in cls and not self._done:
            self._d = 1
            self.parts.append("\n")
        if (self._d or self._rt in self.BLOCKS) and tag in self.NL:
            self.parts.append("\n")
        if "t-slds__bgimg" in cls and a.get("data-original") and a["data-original"] not in self.imgs:
            self.imgs.append(a["data-original"])

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self._skip:
            self._skip -= 1
        if self._d and tag not in VOID:
            self._d -= 1
            if not self._d:
                self._done = True
                self.parts.append("\n")
        if self._rt in self.BLOCKS and tag in self.NL:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._d or self._rt in self.BLOCKS:
            self.parts.append(data)

    def text(self):
        t = "".join(self.parts)
        t = re.sub(r"[^\S\n]+", " ", t)
        t = re.sub(r" ?\n ?", "\n", t)
        t = re.sub(r"\n+", "\n", t)
        return t.strip()


def fetch_page(url):
    """Возвращает (описание, [фото]) со страницы товара или (None, None) при ошибке."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        p = PageParser()
        p.feed(html)
        time.sleep(0.7)
        return (p.text()[:5000] or None), (p.imgs or None)
    except Exception as e:  # страница недоступна - останутся данные из основы
        print("page fail:", url, e)
        return None, None


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
            pdesc, pimgs = fetch_page(link.replace("http://", "https://")) if FETCH_PAGES else (None, None)
            desc = pdesc or b["desc"]
            imgs = pimgs or b["imgs"] or imgs_of(v)
        else:
            avail, price, title, link = "out of stock", b["price"], b["title"], b["link"]
            pdesc, pimgs = fetch_page(link.replace("http://", "https://")) if FETCH_PAGES else (None, None)
            desc, imgs = pdesc or b["desc"], pimgs or b["imgs"]
        items.append(item(sku, title, desc, link, imgs, avail, price))
    for sku, v in vis.items():  # новые товары, которых нет в основе
        if sku in seen:
            continue
        q = str(v.get("quantity", "")).strip()
        link = v.get("url") or ""
        pdesc, pimgs = fetch_page(link) if (FETCH_PAGES and link) else (None, None)
        items.append(item(sku, v["title"], pdesc or v.get("descr") or v.get("text") or "", link,
                          pimgs or imgs_of(v), "out of stock" if q == "0" else "in stock", money(v["price"])))
    head = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">\n<channel>\n'
            '<title>Banch</title>\n<link>https://banch.com.ua</link>\n'
            '<description>%s</description>\n' % escape(SHOP_DESC))
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
