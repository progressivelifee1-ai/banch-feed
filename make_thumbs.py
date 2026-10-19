import io, json, glob, base64, hashlib, re, urllib.request, concurrent.futures as cf
from PIL import Image
N = 8
H = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
def shard(u):
    return int(hashlib.md5(u.encode()).hexdigest(), 16) % N
cache = {}
for f in glob.glob("docs/bth*.json"):
    try:
        cache.update(json.load(open(f)))
    except Exception:
        pass
urls = set()
for r in json.load(open("docs/hubdata.json")):
    for part in (r[6], r[7]["i"]):
        urls.update(u for u in part.split("|") if u)
def thumb(u):
    m = re.match(r"https://static\.tildacdn\.(?:net|com)/(tild[^/]+)/(.+)$", u)
    return "https://thb.tildacdn.net/%s/-/resize/100x/%s" % (m.group(1), m.group(2)) if m else None
def get(u):
    t = thumb(u)
    if not t:
        return u, None
    for _ in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(t, headers=H), timeout=30).read()
            im = Image.open(io.BytesIO(b)).convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.split()[3])
            bg.thumbnail((80, 80))
            o = io.BytesIO()
            bg.save(o, "JPEG", quality=50, optimize=True)
            return u, "data:image/jpeg;base64," + base64.b64encode(o.getvalue()).decode()
        except Exception:
            pass
    return u, None
todo = [u for u in urls if u not in cache]
print("need", len(todo), "cached", len(cache))
with cf.ThreadPoolExecutor(8) as ex:
    for u, d in ex.map(get, todo):
        if d:
            cache[u] = d
shards = [{} for _ in range(N)]
for u in urls:
    if u in cache:
        shards[shard(u)][u] = cache[u]
for i, s in enumerate(shards):
    json.dump(s, open("docs/bth%d.json" % i, "w"), ensure_ascii=False, separators=(",", ":"))
print("done", sum(len(s) for s in shards), "of", len(urls))
