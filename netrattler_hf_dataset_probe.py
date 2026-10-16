#!/usr/bin/env python3
"""Read-only: inspect candidate Hugging Face football datasets (files, columns, row counts,
date range, sample row). Writes a summary to netrattler_card_diag (probe=hf_dataset_probe)."""
import io, json, os, sys
import pandas as pd
import requests

IDS = sys.argv[1:] or [
    "oliviersportsdata/European-Football-Timestamped-Odds-Pinnacle-Match-Stats",
    "minmaxxxer/premier-league-odds-2026-27",
    "minmaxxxer/premier-league-closing-odds-2025-26",
    "minmaxxxer/laliga-serie-a-bundesliga-closing-odds-2025-26",
    "xgmind/premier-league-xg-audit",
]
UA = {"User-Agent": "NETRATTLER-HF-Probe/1.0"}
DATE_COLS = ("date", "match_date", "Date", "kickoff", "commence_time", "datetime", "timestamp", "utc_date")


def read_any(url, name):
    r = requests.get(url, headers=UA, timeout=90)
    r.raise_for_status()
    b = io.BytesIO(r.content)
    if name.endswith(".parquet"):
        return pd.read_parquet(b)
    if name.endswith(".jsonl"):
        return pd.read_json(b, lines=True)
    if name.endswith(".json"):
        return pd.read_json(b)
    return pd.read_csv(b, low_memory=False)


def main():
    out = {"probe": "hf_dataset_probe"}
    for did in IDS:
        res = {}
        try:
            meta = requests.get(f"https://huggingface.co/api/datasets/{did}", headers=UA, timeout=30).json()
            files = [s["rfilename"] for s in meta.get("siblings") or []]
            data_files = [f for f in files if f.endswith((".csv", ".parquet", ".jsonl", ".json")) and "dataset_info" not in f]
            res.update({"files": len(files), "data_files": data_files[:15], "last_modified": meta.get("lastModified"),
                        "license": (meta.get("cardData") or {}).get("license"), "gated": meta.get("gated")})
            card = requests.get(f"https://huggingface.co/datasets/{did}/raw/main/README.md", headers=UA, timeout=30)
            res["readme"] = card.text[:900] if card.ok else ""
            if data_files:
                # largest-looking/most recent file first: prefer names with 2026
                pick = sorted(data_files, key=lambda f: ("2026" in f, "2025" in f, f), reverse=True)[0]
                df = read_any(f"https://huggingface.co/datasets/{did}/resolve/main/{pick}", pick)
                res["picked"] = pick
                res["rows"] = int(len(df))
                res["columns"] = [str(c) for c in df.columns][:60]
                for c in df.columns:
                    if str(c) in DATE_COLS or "date" in str(c).lower():
                        d = pd.to_datetime(df[c], errors="coerce", utc=True).dropna()
                        if len(d):
                            res["date_col"] = str(c)
                            res["date_min"], res["date_max"] = str(d.min())[:10], str(d.max())[:10]
                            break
                res["sample"] = json.loads(df.head(2).to_json(orient="records", date_format="iso"))
        except Exception as exc:
            res["err"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        out[did] = res
        print(did, json.dumps({k: v for k, v in res.items() if k not in ("sample", "readme")}, default=str)[:900], flush=True)
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=30, json={"info": json.loads(json.dumps(out, default=str))},
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})


if __name__ == "__main__":
    main()
