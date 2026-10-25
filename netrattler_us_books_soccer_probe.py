"""Read-only Probe: bieten DraftKings (offener Sportsbook-JSON-Feed) und Bovada Fussball-Spielerprops
(shots, shots on target, tackles, fouls)? Nur einfache GET-Requests wie ein normaler Browser-Aufruf der Seite,
wenige Requests, KEINE Browser-Imitation, KEIN Proxy, KEIN Umgehen: bei 403/429 wird nur das Ergebnis protokolliert.
Schreibt nur eine Diagnosezeile."""
import os, re, requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"Accept": "application/json", "User-Agent": "NETRATTLER-probe/1.0"}
DK = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1"
HINT = re.compile(r"shot|tackle|foul|card|assist|goal|save|offside|cross|pass", re.I)


def get(url, params=None):
    try:
        r = requests.get(url, params=params, headers=H, timeout=20)
        try:
            j = r.json()
        except Exception:
            j = None
        return r.status_code, j
    except Exception as e:
        return type(e).__name__, None


def main():
    out = {"probe": "us_books_soccer"}
    # DraftKings: Liga-Seiten fuer Fussball (EPL / Champions League / La Liga / Bundesliga / Serie A)
    dk = {}
    for name, lid in (("EPL", "40253"), ("UCL", "40685"), ("LaLiga", "40031"), ("Bundesliga", "40481"), ("SerieA", "40030")):
        st, j = get(f"{DK}/leagues/{lid}")
        info = {"http": st}
        if isinstance(j, dict):
            cats = {str(c.get("id")): str(c.get("name") or "") for c in j.get("categories", []) if isinstance(c, dict)}
            subs = [f"{cats.get(str(s.get('categoryId')), '')}/{s.get('name')}" for s in j.get("subcategories", []) if isinstance(s, dict)]
            info["n_events"] = len(j.get("events", []) or [])
            info["cats"] = sorted(set(cats.values()))[:20]
            info["prop_subcats"] = [s for s in subs if HINT.search(s)][:25]
        dk[name] = info
    out["draftkings"] = dk
    # Bovada: Fussball-Coupon
    bov = {}
    for name, path in (("EPL", "soccer/england/premier-league"), ("UCL", "soccer/europe/uefa-champions-league")):
        st, j = get(f"https://www.bovada.lv/services/sports/event/coupon/events/A/description/{path}", {"marketFilterId": "def", "lang": "en"})
        info = {"http": st}
        if isinstance(j, list) and j:
            evs = (j[0] or {}).get("events", []) or []
            info["n_events"] = len(evs)
            groups = set()
            for e in evs[:6]:
                for dg in e.get("displayGroups", []) or []:
                    groups.add(str(dg.get("description")))
            info["groups"] = sorted(groups)[:25]
        bov[name] = info
    out["bovada"] = bov
    print(out)
    if SB and SK:
        try:
            requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=15,
                          headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"},
                          json={"info": out})
        except Exception:
            pass


if __name__ == "__main__":
    main()
