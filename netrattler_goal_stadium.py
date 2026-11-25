"""Goal Hunter on the exact empty owner stadium. Offline until sender integration.
The caller must verify player/club and fixture provenance before supplying bytes.
"""
from io import BytesIO
import math
from PIL import Image, ImageDraw, ImageChops
from netrattler_stadium_portrait import load_master, _label, _crest, _verified_time, GOLD, WHITE, CYAN
from netrattler_premium_telegram_adapter import _crest as decode_crest
from netrattler_premium_live_bridge import _book_price, _split_match, _raw_asset
from netrattler_btts_owner_original import _percent
from netrattler_visual_gate import club_same
from netrattler_scorer_qualification import qualifies

def render_goal(tip, *, crest_provider, player_provider, result=None):
    home, away = _split_match(tip.get("match"))
    name = str(tip.get("player") or "").strip()
    team = str(tip.get("team") or "").strip()
    if not name or not team or sum(club_same(team,t) for t in (home,away)) != 1:
        raise ValueError("Verified player club must identify exactly one team")
    kickoff = _verified_time({"commence_time":tip.get("_kickoff") or tip.get("commence_time") or tip.get("kickoff_utc")})
    if not kickoff:
        raise ValueError("Verified timezone-aware kickoff required")
    price, source = _book_price(tip)
    probability = _percent(tip.get("probability"),strict=True)
    p=float(probability.rstrip("%"))
    eligible, reason=qualifies(price,p,source)
    if not eligible:
        raise ValueError("Goal Hunter selection rejected: "+reason)
    fair=100/p
    supplied=tip.get("fairOdds",tip.get("fair_odds"))
    if supplied is not None and (not math.isfinite(float(supplied)) or abs(float(supplied)-fair)>.1):
        raise ValueError("Inconsistent fair quote")
    gpg=float(tip.get("goals_per_game"))
    if not math.isfinite(gpg) or gpg<0:
        raise ValueError("Measured goals per game required")
    original=load_master()
    canvas=original.copy()
    # Reuse the established Goal Hunter geometry: central player, side crests,
    # player name beneath, four metric columns. No panels, rings or backdrop.
    portrait=_raw_asset(player_provider(name,team),"player",80)
    if not isinstance(portrait,Image.Image):
        raise ValueError("Missing verified player cutout")
    alpha=portrait.getchannel("A")
    bbox=alpha.point(lambda v:255 if v>=24 else 0).getbbox()
    if not bbox: raise ValueError("Empty portrait")
    portrait=portrait.crop(bbox)
    if min(portrait.size)<60: raise ValueError("Player cutout too small")
    scale=min(432/portrait.width,390/portrait.height)
    if scale>4: raise ValueError("Player resolution too low")
    portrait=portrait.resize((round(portrait.width*scale),round(portrait.height*scale)),Image.Resampling.LANCZOS)
    canvas.paste(portrait,((1122-portrait.width)//2,730-portrait.height),portrait)
    for club,x in ((home,190),(away,932)):
        _crest(canvas,decode_crest(crest_provider(club)),(x,530))
    d=ImageDraw.Draw(canvas)
    _label(d,(561,300),"GOAL HUNTER",850,56,GOLD)
    _label(d,(190,680),home,290,35)
    _label(d,(932,680),away,290,35)
    _label(d,(561,780),name.upper(),1000,58)
    _label(d,(561,845),kickoff,960,33)
    for x,label,value in ((155,"QUOTE",f"@{price:.2f}"),(425,"MODELL",probability),
                          (695,"FAIR",f"{fair:.2f}"),(965,"TORE/SPIEL",f"{gpg:.2f}")):
        _label(d,(x,945),label,248,27,CYAN)
        _label(d,(x,1005),value,248,42,GOLD)
    mark=str(((result or {}).get("marks") or {}).get("0") or "").lower()
    status={"won":"GEWONNEN","win":"GEWONNEN","lost":"VERLOREN","loss":"VERLOREN","push":"PUSH","void":"VOID"}.get(mark,"OFFEN")
    _label(d,(561,1215),"AUSWERTUNG: "+status,920,38,GOLD)
    _label(d,(561,1260),str((result or {}).get("ft") or ""),900,28)
    if ImageChops.difference(canvas.crop((0,0,1122,265)),original.crop((0,0,1122,265))).getbbox():
        raise AssertionError("Owner header modified")
    out=BytesIO()
    canvas.save(out,format="PNG",optimize=True)
    return out.getvalue()
