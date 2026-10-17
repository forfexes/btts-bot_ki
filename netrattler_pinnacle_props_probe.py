"""Schema probe for Pinnacle guest-API player specials (read-only, bounded, honest UA).
Writes samples + description stats to netrattler_card_diag (probe=pinnacle_props_probe)."""
import collections, json, os, re
import requests

B = "https://guest.api.arcadia.pinnacle.com/0.1"
H = {"User-Agent": "Mozilla/5.0 NETRATTLER-research/1.0", "Accept": "application/json",
     "x-api-key": os.getenv("PINNACLE_GUEST_KEY", ""), "Referer": "https://www.pinnacle.com/"}
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
out = {"probe": "pinnacle_props_probe"}

ms = requests.get(f"{B}/sports/29/matchups", headers=H, timeout=60).json()
specials = [m for m in ms if m.get("type") == "special"]
pp = [m for m in specials if str((m.get("special") or {}).get("category")) in ("Player Props", "Goalscorer")]
out["n_specials"], out["n_player_specials"] = len(specials), len(pp)
# Description patterns with the player name stripped to a placeholder
pat = collections.Counter()
for m in pp:
    d = str((m.get("special") or {}).get("description") or "")
    pat[re.sub(r"^[A-Z][^()]*?(?= (?:Total|To |Shots|Shot|Goals|Assists|Fouls|Tackles|Cards|Booked|Saves|Passes|Points|Anytime|First|Last))", "<P>", d)[:60]] += 1
out["desc_patterns"] = pat.most_common(40)
out["sample_specials"] = [{k: m.get(k) for k in ("id", "parentId", "parent", "special", "participants", "units", "league", "startTime", "isLive")} for m in pp[:3]]
parents = collections.Counter(m.get("parentId") or (m.get("parent") or {}).get("id") for m in pp)
out["parents_with_props"] = len(parents)
pid = parents.most_common(1)[0][0] if parents else None
out["probe_parent"] = pid
if pid:
    rel = requests.get(f"{B}/matchups/{pid}/related", headers=H, timeout=30)
    out["related_http"] = rel.status_code
    rj = rel.json() if rel.ok else []
    out["related_n"] = len(rj) if isinstance(rj, list) else 0
    mk = requests.get(f"{B}/matchups/{pid}/markets/related/straight", headers=H, timeout=30)
    out["markets_http"] = mk.status_code
    mj = mk.json() if mk.ok else []
    out["markets_n"] = len(mj) if isinstance(mj, list) else 0
    # one special + its market
    sp_ids = {m["id"] for m in pp if (m.get("parentId") or (m.get("parent") or {}).get("id")) == pid}
    out["market_samples"] = [x for x in mj if isinstance(x, dict) and x.get("matchupId") in sp_ids][:3]
    out["special_samples_for_parent"] = [{k: m.get(k) for k in ("id", "special", "participants", "units")} for m in pp if m["id"] in sp_ids][:3]
s = json.dumps(out)[:60000]
print(s[:5000])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}, json={"info": json.loads(s) if s.endswith("}") else {"probe": "pinnacle_props_probe", "truncated": s[:50000]}})
