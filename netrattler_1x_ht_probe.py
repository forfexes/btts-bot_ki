"""Read-only: find 1xBet-platform 1st-half BTTS / total event type codes. Writes to netrattler_card_diag."""
import os, json, requests, datetime
import netrattler_keyless_odds as k

def main():
    out = {"probe": "1x_ht", "hosts": {}}
    for host in k.X1_HOSTS:
        js, st = k._get(f"{host}/service-api/LineFeed/Get1x2_VZip",
                        {"sports": "1", "count": "30", "lng": "en", "mode": "4", "country": "1", "getEmpty": "true"})
        games = [g for g in (js or {}).get("Value") or [] if g.get("I") and not g.get("SC")][:6]
        found = {}
        for g in games:
            gj, gs = k._get(f"{host}/service-api/LineFeed/GetGameZip",
                            {"id": str(g["I"]), "lng": "en", "isSubGames": "true", "GroupEvents": "true",
                             "countevents": "250", "grMode": "2"})
            v = (gj or {}).get("Value") or {}
            for grp in v.get("GE") or []:
                gid = grp.get("G")
                for arr in grp.get("E") or []:
                    for e in arr:
                        found.setdefault(f"G{gid}/T{e.get('T')}", {"P": e.get("P"), "C": e.get("C")})
            names = {str(x.get("G")): x.get("GN") for x in v.get("SG") or []}
            sub = [(s.get("PN") or s.get("TG"), s.get("I")) for s in v.get("SG") or []][:15]
            found["_sub"] = sub
            for s_ in v.get("SG") or []:
                if str(s_.get("PN") or "").lower().startswith("1st"):
                    hj, _ = k._get(f"{host}/service-api/LineFeed/GetGameZip",
                                   {"id": str(s_["I"]), "lng": "en", "GroupEvents": "true", "countevents": "250", "grMode": "2"})
                    hv = (hj or {}).get("Value") or {}
                    for grp in hv.get("GE") or []:
                        for arr in grp.get("E") or []:
                            for e in arr:
                                found.setdefault(f"HT_G{grp.get('G')}/T{e.get('T')}", {"P": e.get("P"), "C": e.get("C")})
                    break
            if any(x.startswith("HT_") for x in found):
                break
        out["hosts"][host] = {"http": st, "games": len(games), "keys": found}
        if games:
            break
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
    body = json.dumps(out, default=str)[:60000]
    print(body[:3000])
    if url and key:
        r = requests.post(f"{url}/rest/v1/netrattler_card_diag",
                          headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"info": out}, timeout=30)
        print("diag", r.status_code)

main()
