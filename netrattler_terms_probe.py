"""Read-only: robots.txt + terms of betexplorer / totalcorner with a plain identified request (no bypass)."""
import os, re, json, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; NetrattlerResearch/1.0)"}
out = {"probe": "terms_probe"}
def get(u):
    try:
        r = requests.get(u, headers=H, timeout=25)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)[:120]
for name, base, terms in (("betexplorer", "https://www.betexplorer.com", ["/terms-of-use/", "/terms/"]),
                          ("totalcorner", "https://www.totalcorner.com", ["/terms", "/api", "/de/api"])):
    c, t = get(base + "/robots.txt")
    out[name + "_robots_http"] = c
    out[name + "_robots"] = t[:1500] if c == 200 else ""
    for p in terms:
        c, t = get(base + p)
        txt = re.sub(r"<[^>]+>", " ", t) if c == 200 else ""
        txt = re.sub(r"\s+", " ", txt)
        hits = [m.group(0) for m in re.finditer(r".{140}(scrap|automat|robot|crawl|spider|reproduc|commercial).{200}", txt, re.I)][:4]
        out[name + p] = {"http": c, "len": len(txt), "hits": hits}
print(json.dumps(out)[:6000])
url = os.environ.get("SUPABASE_URL", "").rstrip("/"); key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
if url and key:
    print(requests.post(url + "/rest/v1/netrattler_card_diag", headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}, json={"info": out}, timeout=30).status_code)
