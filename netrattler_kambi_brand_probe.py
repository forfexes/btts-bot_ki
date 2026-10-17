"""Probe: which public Kambi brand codes answer, how many football events and player-prop offers each has. Read-only."""
import json, os, re
import requests

HOST = "https://eu-offering-api.kambicdn.com"
BRANDS = ["ub", "ubse", "ubnl", "ubau", "ubfr", "ubbe", "ubuk", "svenskaspel", "rsiuspa", "888", "888sport", "paf", "leovegas", "nb", "bs",
          "betsson", "mrgreen", "casumo", "betsafe", "coolbet", "ngs", "ngsuk", "pafes", "pafit", "pafuk", "bwin", "tipico", "veikkaus", "atg", "kindred"]
H = {"User-Agent": "NETRATTLER-research/1.0", "Accept": "application/json"}
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
res = {}
for b in BRANDS:
    r = {}
    try:
        u = f"{HOST}/offering/v2018/{b}/listView/football/all/all/all/matches.json"
        resp = requests.get(u, headers=H, params={"lang": "en_GB", "market": "GB", "useCombined": "true"}, timeout=20)
        r["http"] = resp.status_code
        if resp.status_code == 200:
            evs = [e.get("event", {}) for e in resp.json().get("events", [])]
            r["events"] = len(evs)
            ids = [e.get("id") for e in evs if e.get("id")][:3]
            labels = set()
            for i in ids:
                d = requests.get(f"{HOST}/offering/v2018/{b}/betoffer/event/{i}.json", headers=H, params={"lang": "en_GB", "market": "GB"}, timeout=20)
                if d.status_code == 200:
                    for o in d.json().get("betOffers", []):
                        l = (o.get("criterion") or {}).get("label", "")
                        if re.search(r"tackle|foul|save|shots|assist|card|score", l, re.I):
                            labels.add(re.sub(r"^.*?(Player's|Player)", r"\1", l)[:60])
            r["player_labels"] = sorted(labels)[:25]
    except Exception as ex:
        r["err"] = str(ex)[:120]
    res[b] = r
out = {"probe": "kambi_brand_probe", "brands": res}
print(json.dumps(out)[:5000])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}, json={"info": out})
