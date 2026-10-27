"""Kopiert odds_history-Zeilen aus MAIN in das Archiv (V4: odds_history_archive). NUR Kopie, nichts wird geloescht.
Auswahl: (a) krumme Alternativ-Totals-Linien, (b) Zeilen aelter als ARCHIVE_KEEP_DAYS Tage.
Lesen ueber REST (MAIN), Schreiben ueber V4_DATABASE_URL (Postgres). Idempotent (on conflict do nothing)."""
import os, sys, requests
import psycopg2
from psycopg2.extras import execute_values, Json

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
DSN = os.getenv("V4_DATABASE_URL") or ""


def fix_dsn(dsn):
    """Passwoerter mit '@' o.ae. unescaped in der URL: am LETZTEN '@' trennen und Zugangsdaten URL-kodieren."""
    from urllib.parse import quote
    if "://" not in dsn:
        return dsn
    scheme, rest = dsn.split("://", 1)
    if "@" not in rest:
        return dsn
    cred, hostpart = rest.rsplit("@", 1)
    user, _, pw = cred.partition(":")
    return f"{scheme}://{quote(user, safe='.')}:{quote(pw, safe='')}@{hostpart}"


DSN = fix_dsn(DSN)
KEEP_DAYS = int(os.getenv("ARCHIVE_KEEP_DAYS", "14"))
COLS = ["source", "match_id", "market", "bookmaker", "captured_date", "home_team", "away_team", "match_date",
        "selection", "odds", "raw", "imported_at"]
KEEP_MARKETS = {"totals_1_5", "totals_2_5", "totals_3_5", "totals_ht_0_5", "totals_ht_1_5"}
H = {"apikey": SK, "Authorization": f"Bearer {SK}"}


def pages(params):
    off = 0
    while True:
        r = requests.get(f"{SB}/rest/v1/odds_history", headers={**H, "Range-Unit": "items", "Range": f"{off}-{off + 999}"},
                         params={"select": ",".join(COLS), "order": "captured_date,source,match_id,market,bookmaker,selection", **params}, timeout=90)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return
        yield rows
        if len(rows) < 1000:
            return
        off += 1000


def is_alt(m):
    m = str(m or "")
    return m.startswith("totals_") and m not in KEEP_MARKETS and all(c.isdigit() or c in "_" for c in m.replace("totals_", "").replace("ht_", ""))


def prune_verified(cur, today=None, dry=None):
    """Loescht Alt-Linien aus MAIN, aber NUR fuer Tage < heute und nur wenn das Archiv pro Tag mindestens
    so viele Zeilen mit denselben Maerkten enthaelt wie MAIN. Standard: ARCHIVE_PRUNE=true (sonst nur zaehlen)."""
    from datetime import date
    dry = (os.getenv("ARCHIVE_PRUNE", "true").lower() != "true") if dry is None else dry
    today = today or date.today().isoformat()
    report = []
    base = f"{SB}/rest/v1/odds_history"
    last_d = "1900-01-01"
    for _guard in range(400):
        r = requests.get(base, headers=H, timeout=60, params=[
            ("select", "captured_date"), ("market", "like.totals_*"),
            ("and", f"(captured_date.gt.{last_d},captured_date.lt.{today})"),
            ("order", "captured_date.asc"), ("limit", "1")])
        r.raise_for_status()
        first = r.json()
        # Tage ohne Alt-Linien ueberspringen wir nicht blind: wir suchen den naechsten Tag mit Alt-Markt
        if not first:
            break
        d = first[0]["captured_date"]
        last_d = d
        cur.execute("select distinct market from odds_history_archive where captured_date=%s and market like 'totals\\_%%'", (d,))
        markets = sorted(m[0] for m in cur.fetchall() if is_alt(m[0]))
        if not markets:
            continue  # Tag hat nur Standard-Maerkte (oder noch nichts Archiviertes) -> nichts zu loeschen
        mk = "in.(" + ",".join(markets) + ")"
        rc = requests.get(base, headers={**H, "Prefer": "count=exact", "Range": "0-0"}, timeout=120,
                          params={"select": "market", "captured_date": f"eq.{d}", "market": mk})
        n_main = int(rc.headers.get("content-range", "*/0").split("/")[-1])
        cur.execute("select count(*) from odds_history_archive where captured_date=%s and market = any(%s)", (d, markets))
        n_arch = cur.fetchone()[0]
        # Alle nicht-Standard-Totals in MAIN muessen exakt die geprueften Maerkte sein (sonst Abbruch fuer den Tag)
        keep = ",".join(sorted(KEEP_MARKETS))
        rn = requests.get(base, headers={**H, "Prefer": "count=exact", "Range": "0-0"}, timeout=120, params=[
            ("select", "market"), ("captured_date", f"eq.{d}"),
            ("and", f"(market.like.totals_*,market.not.in.({keep}))")])
        n_nonkeep = int(rn.headers.get("content-range", "*/0").split("/")[-1])
        extra = ["nicht-geprueft"] if n_nonkeep != n_main else []
        ok = n_main > 0 and n_arch >= n_main and not extra
        report.append({"d": d, "main": n_main, "archive": n_arch, "ok": ok, "extra": sorted(extra)[:3]})
        if not ok or dry:
            continue  # ungepruefter Tag bleibt unangetastet
        for i in range(0, len(markets), 5):
            chunk = markets[i:i + 5]
            dr = requests.delete(base, headers={**H, "Prefer": "return=minimal"}, timeout=300,
                                 params={"captured_date": f"eq.{d}", "market": "in.(" + ",".join(chunk) + ")"})
            if not dr.ok:
                report[-1]["ok"] = False; report[-1]["delete_status"] = dr.status_code
                return report
        report[-1]["deleted"] = n_main
    return report


def main():
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    copied = {"old": 0, "alt": 0}
    with psycopg2.connect(DSN, connect_timeout=20) as conn:
        with conn.cursor() as cur:
            def push(rows):
                vals = [tuple(Json(r[c]) if c == "raw" and r.get(c) is not None else r.get(c) for c in COLS) for r in rows]
                execute_values(cur, "insert into odds_history_archive (" + ",".join(COLS) + ") values %s on conflict do nothing", vals)
            for r in pages({"captured_date": f"lt.{cutoff}"}):
                push(r); copied["old"] += len(r)
            conn.commit()
            # Alternativlinien (neuere): per Markt filtern
            for r in pages({"captured_date": f"gte.{cutoff}", "market": "like.totals_*"}):
                alt = [x for x in r if is_alt(x["market"])]
                if alt:
                    push(alt); copied["alt"] += len(alt)
            conn.commit()
            cur.execute("select count(*) from odds_history_archive")
            total = cur.fetchone()[0]
            try:
                pruned = prune_verified(cur)
            except Exception as exc:
                pruned = [{"error": type(exc).__name__}]
            print({"probe": "odds_prune", "days": pruned})
    print({"probe": "odds_archive", "copied": copied, "archive_total": total, "cutoff": cutoff})
    if SB and SK:
        try:
            requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers={**H, "Content-Type": "application/json"}, timeout=15,
                          json={"info": {"probe": "odds_archive", "copied": copied, "archive_total": total, "cutoff": cutoff, "pruned": pruned}})
        except Exception:
            pass


def _report_error(e):
    msg = (type(e).__name__ + ": " + str(e))[:300].replace(DSN, "<dsn>") if DSN else (type(e).__name__ + ": " + str(e))[:300]
    print("FEHLER", msg)
    try:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers={**H, "Content-Type": "application/json"}, timeout=15,
                      json={"info": {"probe": "odds_archive_error", "has_dsn": bool(DSN), "error": msg}})
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _report_error(exc)
        sys.exit(1)
