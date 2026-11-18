"""Read-only Wikimedia Commons attribution inventory for NETRATTLER.

Source roster: existing data/player_season_2026_2027.csv (no new paid datasets).
Writes a local CSV of candidate images; NEVER posts pictures or marks a source
image as licensed for Telegram without review. Does not persist to Supabase.
Usage: python netrattler_commons_inventory.py --limit 50 --output /tmp/commons.csv
"""
import argparse
import csv
import html
import re
import time
from pathlib import Path
from urllib.parse import quote
import requests

from netrattler_commons_photos import normalize

API = "https://commons.wikimedia.org/w/api.php"
FIELDS = ["Spieler", "Verein", "Position", "Bild_URL", "Lizenz", "Fotograf",
          "Commons_Seite", "Lizenz_URL", "Pruefstatus"]
HEADERS = {"User-Agent": "NETRATTLER-photo-inventory/1.0 (metadata research)"}


def clean_html(text):
    return re.sub(r"<[^>]+>", "", html.unescape(str(text or ""))).strip()


def metadata_value(info, field):
    return clean_html(((info.get("extmetadata") or {}).get(field) or {}).get("value"))


def candidate_row(player, club, page, position=""):
    title = str(page.get("title") or "")
    if not title.startswith("File:"):
        return None
    # A Commons search hit isn't proof of identity. Only exact full-name
    # filename matches become candidates; all stay pending review.
    if not re.search(r"(?<![a-z0-9])" + re.escape(normalize(player)) + r"(?![a-z0-9])",
                     normalize(title[5:])):
        return None
    info = (page.get("imageinfo") or [{}])[0]
    url = info.get("thumburl") or info.get("url") or ""
    if not str(url).startswith("https://upload.wikimedia.org/"):
        return None
    license_name = metadata_value(info, "LicenseShortName")
    credit = metadata_value(info, "Artist")
    license_url = ((info.get("extmetadata") or {}).get("LicenseUrl") or {}).get("value") or ""
    return {
        "Spieler": player, "Verein": club, "Position": position, "Bild_URL": url,
        "Lizenz": license_name, "Fotograf": credit,
        "Commons_Seite": "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_"), safe=":()_,"),
        "Lizenz_URL": str(license_url),
        "Pruefstatus": "manuell_pruefen" if license_name and credit else "metadaten_unvollstaendig",
    }


def search_commons(session, name, club, max_pages=3, position=""):
    """Read bounded paginated Commons results; never infer licensing from categories."""
    params = {
        "action": "query", "generator": "search",
        "gsrsearch": 'filetype:bitmap "' + name + '"',
        "gsrnamespace": 6, "gsrlimit": 50,
        "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": 450, "format": "json", "formatversion": 2,
    }
    found = {}
    for _ in range(max(1, min(int(max_pages), 5))):
        response = session.get(API, params=params, headers=HEADERS, timeout=20)
        response.raise_for_status()
        body = response.json()
        for page in (body.get("query") or {}).get("pages") or []:
            row = candidate_row(name, club, page, position=position)
            if row:
                found[row["Commons_Seite"]] = row
        continuation = body.get("continue")
        if not continuation or not isinstance(continuation, dict):
            break
        params.update(continuation)
    return list(found.values())


def roster(path, limit, start=0):
    """Yield deduplicated player/club/position rows, with a stable batch offset."""
    seen = set()
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("Player") or row.get("Spieler") or row.get("Name") or "").strip()
            club = (row.get("Squad") or row.get("Verein") or row.get("Team") or "").strip()
            position = (row.get("Pos") or row.get("Position") or "").strip()
            identity = (normalize(name), normalize(club))
            if not all(identity) or identity in seen:
                continue
            seen.add(identity)
            if len(seen) <= start:
                continue
            yield name, club, position
            if len(seen) >= start + limit:
                return


def build(source, output, limit=50, pause=1.0, session=None, start=0,
          resume=False, max_pages=3):
    """Write only public metadata; resume skips complete player/club records."""
    if not 1 <= limit <= 10000 or start < 0 or not 1 <= max_pages <= 5:
        raise ValueError("invalid batch bounds (limit 1..10000, pages 1..5)")
    session = session or requests.Session()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if resume and output.is_file():
        with output.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                seen.add((normalize(row.get("Spieler")), normalize(row.get("Verein"))))
    append = resume and output.is_file() and output.stat().st_size > 0
    count = 0
    with output.open("a" if append else "w", encoding="utf-8-sig" if not append else "utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not append:
            writer.writeheader()
        for name, club, position in roster(source, limit, start=start):
            if (normalize(name), normalize(club)) in seen:
                continue
            try:
                rows = search_commons(session, name, club, max_pages=max_pages,
                                      position=position)
                if rows:
                    for row in rows:
                        writer.writerow(row)
                        count += 1
                else:
                    writer.writerow({"Spieler": name, "Verein": club, "Position": position,
                                     "Pruefstatus": "kein_eindeutiger_kandidat"})
            except (requests.RequestException, ValueError, TypeError):
                writer.writerow({"Spieler": name, "Verein": club, "Position": position,
                                 "Pruefstatus": "api_fehler"})
            handle.flush()  # Keep completed players even if the action is interrupted.
            if pause:
                time.sleep(max(0, pause))
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/player_season_2026_2027.csv")
    parser.add_argument("--output", default="/tmp/netrattler_commons_inventory.csv")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--start", type=int, default=0, help="0-based player offset")
    parser.add_argument("--resume", action="store_true", help="Append and skip completed names")
    parser.add_argument("--pages", type=int, default=3, help="1 to 5 Commons API result pages per player")
    args = parser.parse_args()
    print("Commons candidates written:", build(args.source, args.output, args.limit, args.pause,
                                              start=args.start, resume=args.resume, max_pages=args.pages))
