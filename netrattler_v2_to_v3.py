"""Kopiert odds_history von V2 nach V3 (Postgres->Postgres). NUR Kopie + Zaehlabgleich, loescht nichts.
Idempotent (on conflict do nothing), fortsetzbar. Env: V2_DATABASE_URL, V3_DATABASE_URL, optional TABLE, BATCH."""
import os, sys, time
import psycopg2
from psycopg2.extras import execute_values
from netrattler_v2_migrate import _parse_dsn, _pooler_variants

TABLE = os.getenv("TABLE", "odds_history")
BATCH = int(os.getenv("BATCH", "5000"))
BUDGET = int(os.getenv("BUDGET_SEC", "1800"))


def connect(dsn):
    p = _parse_dsn(dsn)
    cands = []
    if p:
        u, pw, h, port, db = p
        cands.append(dict(user=u, password=pw, host=h, port=int(port), dbname=db))
    cands += _pooler_variants(dsn)
    last = None
    for kw in cands:
        try:
            return psycopg2.connect(connect_timeout=20, sslmode="require", **kw)
        except Exception as e:
            last = e
    raise last


def _diag(info):
    import requests
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/"); key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        try:
            r = requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=20, json={"info": info},
                              headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            print("diag status", r.status_code)
        except Exception as exc:
            print("diag error", type(exc).__name__)
    else:
        print("diag: kein SUPABASE_URL/KEY")


def count_only():
    v2 = connect(os.environ["V2_DATABASE_URL"]); v3 = connect(os.environ["V3_DATABASE_URL"])
    out = {"probe": "v2_v3_count", "table": TABLE}
    for name, c in (("v2", v2), ("v3", v3)):
        cur = c.cursor()
        cur.execute(f"select count(*), min(captured_date)::text, max(captured_date)::text from {TABLE}")
        n, a, b = cur.fetchone(); out[name] = {"rows": n, "min": a, "max": b}
    out["complete"] = out["v3"]["rows"] >= out["v2"]["rows"]
    print(out); _diag(out)


def main():
    if os.getenv("MODE") == "count":
        return count_only()
    v2 = connect(os.environ["V2_DATABASE_URL"]); v3 = connect(os.environ["V3_DATABASE_URL"])
    c2 = v2.cursor(); c3 = v3.cursor()
    c2.execute("select column_name from information_schema.columns where table_name=%s order by ordinal_position", (TABLE,))
    cols = [r[0] for r in c2.fetchall()]
    c2.execute("select pg_get_indexdef(i.indexrelid) from pg_index i where i.indrelid=%s::regclass and i.indisprimary", (TABLE,))
    print("cols", cols)
    c3.execute("select to_regclass(%s)", (TABLE,))
    if c3.fetchone()[0] is None:
        # Schema aus der Spaltenliste von V2 (typen aus information_schema)
        c2.execute("select column_name, data_type from information_schema.columns where table_name=%s order by ordinal_position", (TABLE,))
        ddl = ", ".join(f'"{n}" {t}' for n, t in c2.fetchall())
        c2.execute("""select a.attname from pg_index i join pg_attribute a on a.attrelid=i.indrelid and a.attnum=any(i.indkey)
                      where i.indrelid=%s::regclass and i.indisprimary order by array_position(i.indkey, a.attnum)""", (TABLE,))
        pk = [r[0] for r in c2.fetchall()]
        c3.execute(f'create table {TABLE} ({ddl}' + (f', primary key ({",".join(pk)})' if pk else "") + ")"); v3.commit()
    collist = ",".join(f'"{c}"' for c in cols)
    name = "cur_" + str(int(time.time()))
    sc = v2.cursor(name=name); sc.itersize = BATCH
    sc.execute(f"select {collist} from {TABLE}")
    t0 = time.time(); n = 0
    while time.time() - t0 < BUDGET:
        rows = sc.fetchmany(BATCH)
        if not rows:
            break
        execute_values(c3, f"insert into {TABLE} ({collist}) values %s on conflict do nothing", rows)
        v3.commit(); n += len(rows)
        if n % 50000 < BATCH:
            print("copied", n, flush=True)
    else:
        print("budget reached; rerun to continue"); 
    c2.execute(f"select count(*) from {TABLE}"); a = c2.fetchone()[0]
    c3.execute(f"select count(*) from {TABLE}"); b = c3.fetchone()[0]
    print({"probe": "v2_to_v3", "table": TABLE, "v2": a, "v3": b, "copied_this_run": n, "complete": b >= a})
    _diag({"probe": "v2_to_v3", "table": TABLE, "v2": a, "v3": b, "copied_this_run": n, "complete": b >= a})
    c3.execute("select pg_size_pretty(pg_database_size(current_database()))"); print("v3 size", c3.fetchone()[0])


if __name__ == "__main__":
    main()
