"""Render verifiable Goal Hunter Telegram photo cards (no fabricated statistics)."""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests

W,H=1080,1350
GOLD=(255,199,45)
CYAN=(28,226,249)
WHITE=(250,251,255)
ORIGINAL_HEADER=Path(__file__).resolve().parent / 'assets' / 'goal_hunter_original_header.webp'

def font(size,bold=True):
    paths=(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    return ImageFont.truetype(paths[0 if bold else 1],size)

def centered(draw,text,y,size=42,color=WHITE,bold=True):
    f=font(size,bold)
    while draw.textbbox((0,0),text,font=f)[2]>W-85 and size>19:
        size-=2
        f=font(size,bold)
    draw.text((W//2,y),text,font=f,fill=color,anchor="mt",stroke_width=1,stroke_fill=(10,12,18))

def panel(draw,coords,color=CYAN,fill=(7,22,37),width=4):
    draw.rounded_rectangle(coords,radius=23,fill=fill,outline=color,width=width)

def crest(team_id):
    if not team_id or not str(team_id).isdigit():
        return None
    url="https://images.fotmob.com/image_resources/logo/teamlogo/"+str(team_id)+".png"
    try:
        r=requests.get(url,timeout=8)
        r.raise_for_status()
        if len(r.content)>1_000_000 or not r.headers.get("Content-Type","").startswith("image/"):
            return None
        im=Image.open(io.BytesIO(r.content)).convert("RGBA")
        im.thumbnail((185,185))
        return im
    except (requests.RequestException,OSError,ValueError):
        return None

def make_card(fixture,metrics=None,*,final_score=None,won=None):
    """Finished cards deliberately omit all statistics; unknown values never rendered."""
    im=Image.new("RGB",(W,H))
    px=im.load()
    for y in range(H):
        for x in range(W):
            glow=max(0,1-abs(x-W/2)/(W/2))
            horizon=max(0,1-abs(y-430)/350)
            px[x,y]=(int(3+7*horizon),int(12+21*horizon+8*glow),int(25+35*horizon))
    d=ImageDraw.Draw(im)
    # Floodlit stadium and luminous grandstand backdrop.
    import random
    rng=random.Random(20261118)
    for side in (0,1):
        for j in range(10):
            x=(20+j*23) if side==0 else (W-20-j*23)
            y=40+j*10
            for radius,color in ((28,(7,88,135)),(14,(45,190,242)),(6,(240,255,255))):
                d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
    for row in range(8):
        y=245+row*47
        d.line((0,y,W,y),fill=(8,61+row*3,99+row*3),width=3)
        for j in range(34):
            x=rng.randrange(0,W)
            d.ellipse((x,y-3,x+3,y),fill=(20,110+rng.randrange(90),155+rng.randrange(90)))
    for y in range(1120,H,14):
        d.line((0,y,W,y),fill=(5,55+(y%35),27),width=3)
    def glow_box(coords,color,fill):
        for spread in (16,10,5):
            d.rounded_rectangle((coords[0]-spread,coords[1]-spread,
                                 coords[2]+spread,coords[3]+spread),
                                radius=24,outline=tuple(int(v*.24) for v in color),width=3)
        d.rounded_rectangle(coords,radius=21,fill=fill,outline=color,width=5)
    # Stadium lightbanks and pitch bands, keeping the original cyan/gold styling.
    for side in (0,1):
        for j in range(8):
            x=(70+j*18) if side==0 else (W-70-j*18)
            d.ellipse((x-8,95+j*8,x+8,111+j*8),fill=(170,245,255))
    for y in range(1180,H,24):
        d.line((0,y,W,y),fill=(9,45,30),width=3)
    # Use the EXACT real photo-sourced NETRATTLER/GOLD GOAL HUNTER header,
    # cropped from the user's approved card, not a drawn imitation.
    if not ORIGINAL_HEADER.is_file():
        raise RuntimeError("Original NETRATTLER image template missing")
    with Image.open(ORIGINAL_HEADER) as original:
        if original.size != (691,169):
            raise RuntimeError("Original template proportions changed")
        header=original.convert("RGB").resize((W,264),Image.Resampling.LANCZOS)
    im.paste(header,(0,0))
    # Only the tiny old subtitle remnants at the bottom of the source crop
    # are covered; the original crown, lettering, floodlights and gold bar stay untouched.
    d=ImageDraw.Draw(im)
    d.rectangle((0,251,W,295),fill=(4,17,31))
    d.line((115,258,965,258),fill=CYAN,width=3)
    centered(d,"LAST MINUTE GOAL",269,38,WHITE)
    centered(d,str(fixture.get("league") or "Fussball"),327,31,WHITE)
    home,away=str(fixture["home"]),str(fixture["away"])
    for name,x,team_id in ((home,195,fixture.get("home_logo_id")),(away,885,fixture.get("away_logo_id"))):
        badge=crest(team_id)
        if badge:
            im.paste(badge,(x-badge.width//2,382),badge)
        else:
            # Never invent a team crest or show a misleading generic FC emblem.
            d.rounded_rectangle((x-78,407,x+78,547),radius=22,outline=CYAN,width=3)
            d.text((x,477),"Wappen",font=font(22),fill=WHITE,anchor="mm")
        f=font(29)
        while d.textbbox((0,0),name,font=f)[2]>385 and f.size>20:
            f=font(f.size-2)
        d.text((x,577),name,font=f,fill=WHITE,anchor="mm")
    glow_box((387,415,693,552),GOLD,(9,12,23))
    score=final_score if final_score is not None else f"{fixture['hg']}:{fixture['ag']}"
    centered(d,"ENDRESULTAT" if final_score is not None else f"{fixture['minute']}'",423,30,GOLD)
    centered(d,str(score),458,77,WHITE)
    if final_score is None:
        glow_box((68,641,1012,990),CYAN,(7,25,41))
        centered(d,"TEAMSTATISTIK",652,39,GOLD)
        teams=(metrics or {}).get("teams") or {}
        rows=[("SCHÜSSE","shots"),("AUFS TOR","sot"),("ECKEN","corners")]
        if all(teams.get(side,{}).get("xg") is not None for side in ("home","away")):
            rows.append(("xG","xg"))
        for i,(label,key) in enumerate(rows):
            yy=722+i*62
            left=teams.get("home",{}).get(key)
            right=teams.get("away",{}).get(key)
            def val(v):
                if v is None:return "–"
                return f"{v:.2f}" if key=="xg" else str(v)
            d.text((215,yy),val(left),font=font(38),fill=WHITE,anchor="mm")
            d.text((W//2,yy),label,font=font(30),fill=GOLD,anchor="mm")
            d.text((865,yy),val(right),font=font(38),fill=WHITE,anchor="mm")
        if not teams.get("home") or not teams.get("away"):
            # ESPN fallback has verified totals but may lack safe team attribution.
            d.rectangle((82,708,998,960),fill=(7,25,41))
            centered(d,"GESAMTSTATISTIK",724,35,GOLD)
            centered(d,f"Schüsse: {(metrics or {}).get('shots','–')}",790,38,WHITE)
            centered(d,f"Aufs Tor: {(metrics or {}).get('sot','–')}",849,38,WHITE)
            if (metrics or {}).get("corners") is not None:
                centered(d,f"Ecken: {metrics['corners']}",909,38,WHITE)
        glow_box((68,1017,1012,1142),GOLD,(20,24,14))
        centered(d,"OVER 0.5 RESTSPIELZEIT",1027,44,GOLD)
        centered(d,str((metrics or {}).get("tier") or "STANDARD"),1092,30,WHITE)
        glow_box((68,1160,1012,1252),CYAN,(6,26,31))
        centered(d,"AUSWERTUNG: OFFEN",1181,39,WHITE)
    else:
        glow_box((68,655,1012,820),GOLD,(20,24,14))
        centered(d,"OVER 0.5 RESTSPIELZEIT",685,45,GOLD)
        centered(d,f"TIPP: {fixture['minute']}' · {fixture['hg']}:{fixture['ag']}",755,32,WHITE)
        glow_box((68,910,1012,1065),(42,244,109) if won else (255,88,92),(7,31,17) if won else (39,9,16))
        centered(d,"AUSWERTUNG",926,40,WHITE)
        centered(d,"GEWONNEN" if won else "VERLOREN",988,62,(45,250,104) if won else (255,85,90))
    centered(d,"@prophunter",1275,36,WHITE)
    output=io.BytesIO()
    im.save(output,format="JPEG",quality=89,optimize=True)
    return output.getvalue()
