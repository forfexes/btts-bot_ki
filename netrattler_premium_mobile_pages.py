"""NETRATTLER AI PREMIUM: Telegram-mobile image pagination; offline only.

One ticket can be shown in 1..3 separate readable image pages; all pages
retain the precise same PNG masthead bytes, ticket identity and global leg
numbering. This is a *preview/export renderer*, not a Telegram publisher.
Only the final page shows the ticket's overall bookmaker quote and 1u stake.
No fallback artwork, synthetic portraits or estimated bookmaker prices.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageDraw

from netrattler_premium_flexible_renderer import (
    validate, MASTER_PATH, MASTER_SHA256, CATEGORIES, MULTI, BG, PANEL,
    GOLD, CYAN, WHITE, _fit, _font, _odds, _asset,
)

MAX_LEGS_PER_IMAGE = 3
ROW_H = 248
GAP = 16
MARGIN = 42
TITLE_H = 112


@dataclass(frozen=True)
class CardPage:
    page: int
    pages: int
    first_leg: int
    last_leg: int
    image: Image.Image


def group_lengths(total: int, max_per_page: int = MAX_LEGS_PER_IMAGE) -> list[int]:
    """Distribute selections evenly, keeping every page <=3 legs by default."""
    if not 1 <= total <= 10 or max_per_page not in (2, 3, 4):
        raise ValueError("Only 1..10 selections and 2..4 per image supported")
    number = math.ceil(total / max_per_page)
    base, extra = divmod(total, number)
    result = [base + (1 if i < extra else 0) for i in range(number)]
    assert sum(result) == total and max(result) <= max_per_page
    return result


def _text(draw, xy, value, max_width, font_size, fill):
    value = str(value or "").strip()
    if value:
        try:
            font = _fit(draw, value, max_width, font_size, min_size=25)
        except ValueError:
            raise ValueError("Card text overflow: field does not fit without overlap") from None
        draw.text(xy, value, font=font, fill=fill)


def _safestatus(raw):
    s = str(raw or "OFFEN").strip().upper()
    if s not in {"OFFEN", "GEWONNEN", "VERLOREN", "VOID", "PUSH", "QA – KEIN TIPP"}:
        raise ValueError("Unknown settlement status")
    return s


def _source(master_path):
    p = Path(master_path)
    if p.resolve() == MASTER_PATH.resolve():
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != MASTER_SHA256:
            raise ValueError("Original NETRATTLER AI PREMIUM masthead has changed")
    with Image.open(p) as opened:
        if opened.format != "PNG" or opened.size != (1080, 608):
            raise ValueError("Master must be the exact 1080x608 PNG dimensions")
        return opened.convert("RGB")


def render_mobile_pages(master_path, ticket, *, max_legs_per_image=MAX_LEGS_PER_IMAGE,
                        preview_only=False):
    """Return CardPage values for ONE ticket; no Telegram posting.

    Production-intended previews (preview_only=False) require two actual team
    badges per leg and authentic player cutout for any named player.
    Synthetic test data are permitted ONLY when preview_only=True and are
    clearly watermarked 'QA / KEIN ECHTER TIPP' on every image.
    """
    kind, legs = validate(ticket)
    if not preview_only:
        for i, leg in enumerate(legs, 1):
            if not (leg.get("home_logo") and leg.get("away_logo")):
                raise ValueError(f"Leg {i}: two authentic club crests required")
            if leg.get("player") and not leg.get("player_photo"):
                raise ValueError(f"Leg {i}: player photo required")
    status = _safestatus(ticket.get("status"))
    master = _source(master_path)
    parts = group_lengths(len(legs), max_legs_per_image)
    pages=[]
    offset=0
    maxpage=len(parts)
    identifier=str(ticket.get("ticket_id") or ticket.get("combined_ticket_id") or "")
    if not preview_only and not identifier:
        raise ValueError("Stable Telegram ticket identity required")
    for index, count in enumerate(parts):
        on_last=index==maxpage-1
        subset=legs[offset:offset+count]
        foot_h=230 if on_last else 150
        top=master.height+29
        title_y=top
        rows_y=title_y+TITLE_H+24
        footer_y=rows_y+(ROW_H+GAP)*count+10
        height=footer_y+foot_h+38
        im=Image.new("RGB",(1080,height),BG)
        im.paste(master,(0,0))
        dr=ImageDraw.Draw(im)
        dr.line((MARGIN,master.height+11,1080-MARGIN,master.height+11),fill=GOLD,width=2)
        dr.rounded_rectangle((MARGIN,title_y,1080-MARGIN,title_y+TITLE_H),
                             radius=18,fill=PANEL,outline=GOLD,width=3)
        title=(kind.replace('_',' ').upper()+
               (f" · {len(legs)} TIPPS" if kind in MULTI else "")+
               (f" · {index+1}/{maxpage}" if maxpage>1 else ""))
        _text(dr,(MARGIN+27,title_y+27),title,950,40,WHITE)
        for j,leg in enumerate(subset):
            y=rows_y+j*(ROW_H+GAP)
            rect=(MARGIN,y,1080-MARGIN,y+ROW_H)
            dr.rounded_rectangle(rect,radius=17,fill=PANEL,outline=CYAN,width=2)
            # Independent transparent image slots; no square/circle mounts.
            if leg.get("home_logo"):
                _asset(im,leg["home_logo"],(MARGIN+15,y+15),(66,69))
            if leg.get("away_logo"):
                _asset(im,leg["away_logo"],(MARGIN+86,y+15),(66,69))
            if leg.get("player_photo"):
                _asset(im,leg["player_photo"],(MARGIN+15,y+92),(136,144))
            # All text starts at x=216, after the separate image column.
            tx=MARGIN+171
            tw=1080-MARGIN-23-tx
            _text(dr,(tx,y+11),f"{offset+j+1:02d}  {leg['match']}",tw,34,WHITE)
            _text(dr,(tx,y+62),leg["market"],tw,37,GOLD)
            if leg.get("player"):
                _text(dr,(tx,y+116),leg["player"],tw,31,WHITE)
            _text(dr,(tx,y+159),f"QUOTE  @{_odds(leg['bookmaker_odds'],'leg'):.2f}",tw,33,CYAN)
            form=str(leg.get("form") or "")
            rowstatus=str(leg.get("result") or "").strip()
            lastline=" · ".join(x for x in (form,rowstatus) if x)
            if lastline:
                _text(dr,(tx,y+205),lastline,tw,28,WHITE)
        dr.rounded_rectangle((MARGIN,footer_y,1080-MARGIN,footer_y+foot_h),
                             radius=17,fill=PANEL,outline=GOLD,width=3)
        if on_last:
            total_quote=_odds(ticket["combined_odds"],"combined") if kind in MULTI else _odds(legs[0]["bookmaker_odds"],"single")
            prob=ticket.get("model_probability")
            probability="—" if prob is None else f"{float(prob):.1f}%"
            summary=(
                (f"GESAMTQUOTE @{total_quote:.2f} · BUCHMACHER",29,GOLD,34),
                (f"MODELLWAHRSCHEINLICHKEIT {probability}",81,CYAN,31),
                ("1 TICKET · 1 UNIT GESAMT",133,WHITE,32),
                ("AUSWERTUNG: "+status,181,WHITE,31),
            )
            for msg,y,color,size in summary:
                _text(dr,(MARGIN+23,footer_y+y),msg,940,size,color)
        else:
            _text(dr,(MARGIN+23,footer_y+22),
                  f"1 TICKET · SEITE {index+1}/{maxpage} · FORTSETZUNG",
                  940,33,GOLD)
            _text(dr,(MARGIN+23,footer_y+76),
                  f"AUSWAHLEN {offset+1}–{offset+count} VON {len(legs)} · 1 UNIT GESAMT",
                  940,30,WHITE)
        if preview_only:
            qa="OFFLINE-QA · KEIN ECHTER TIPP · NICHT TELEGRAM"
            dr.text((MARGIN+4,height-30),qa,font=_fit(dr,qa,950,23,min_size=20),fill=GOLD)
        if im.crop((0,0,master.width,master.height)).tobytes()!=master.tobytes():
            raise AssertionError("Protected premium masthead changed")
        pages.append(CardPage(index+1,maxpage,offset+1,offset+count,im))
        offset+=count
    assert offset==len(legs)
    return pages


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--master",type=Path,default=MASTER_PATH)
    parser.add_argument("--data",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--preview-only",action="store_true")
    args=parser.parse_args()
    card=json.loads(args.data.read_text(encoding="utf8"))
    pages=render_mobile_pages(args.master,card,preview_only=args.preview_only)
    args.output_dir.mkdir(exist_ok=True,parents=True)
    manifest=[]
    for page in pages:
        output=args.output_dir/f"netrattler_{card['category']}_{page.page:02d}-of-{page.pages:02d}.png"
        page.image.save(output,optimize=True)
        manifest.append({"file":output.name,"page":page.page,"pages":page.pages,
                         "first_leg":page.first_leg,"last_leg":page.last_leg,
                         "size":page.image.size})
    print(json.dumps({"telegram_sent":False,"pages":manifest},ensure_ascii=False))


if __name__=="__main__":
    main()