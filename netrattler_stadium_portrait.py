"""Render only on the exact owner-selected, data-free stadium PNG.

No screenshot patches, replacement master, external calls or Telegram access.
The file must be uploaded verbatim to the pinned repository path.
"""
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import math

from PIL import Image, ImageDraw, ImageFont, ImageChops

MASTER = Path(__file__).resolve().parent / "assets/premium_master/netrattler_stadium_portrait_20261124.png"
DIGEST = "9bcbaec6083297aec9c8ae7c341d633c115bc78c28e5f526d7eb2bd7d587cd72"
DIMENSIONS = (1122, 1402)
VERSION = "stadium-portrait-20261124"
REGULAR = frozenset({"btts", "over25", "btts_ht", "over15_ht", "1x2", "var"})
TITLES = {"btts":"BTTS", "over25":"OVER 2.5", "btts_ht":"BTTS · 1. HALBZEIT",
          "over15_ht":"OVER 1.5 · 1. HALBZEIT", "1x2":"1X2", "var":"VAR"}
GOLD = (255,218,104)
WHITE = (250,251,255)
CYAN = (58,211,247)

def load_master(path=None):
    path = MASTER if path is None else Path(path)
    if not path.is_file():
        raise ValueError("owner_stadium_master_missing: " + MASTER.name)
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != DIGEST:
        raise ValueError("owner_stadium_master_sha256_mismatch")
    with Image.open(BytesIO(raw)) as source:
        if source.format != "PNG" or source.size != DIMENSIONS:
            raise ValueError("owner_stadium_master_dimensions_mismatch")
        return source.convert("RGB")

def master_ready():
    try:
        load_master()
        return True
    except (ValueError,OSError):
        return False

def font(size):
    for name in ("DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    raise ValueError("Required scalable stadium card font missing")

def _label(draw, xy, value, width, size, color=WHITE):
    value = str(value or "").strip()
    if not value:
        return
    if "\n" in value or len(value)>140:
        raise ValueError("Invalid one-line source label")
    for n in range(size, 21, -1):
        f=font(n)
        if draw.textlength(value,font=f)+4<=width:
            draw.text(xy,value,font=f,anchor="mm",fill=color,stroke_width=1,stroke_fill=(3,13,26))
            return
    raise ValueError("Verified label does not fit original stadium slot")

def _crest(canvas, crest, center):
    # Upstream adapter has already verified authentic transparent crest bytes.
    rgba = crest.convert("RGBA")
    if rgba.getchannel("A").getextrema()[0] == 255:
        raise ValueError("Opaque crest forbidden")
    scale = min(220 / rgba.width, 220 / rgba.height)
    if scale > 4:
        raise ValueError("Crest too small for original stadium")
    rgba = rgba.resize((round(rgba.width*scale),round(rgba.height*scale)), Image.Resampling.LANCZOS)
    canvas.paste(rgba,(center[0]-rgba.width//2,center[1]-rgba.height//2),rgba)

def _verified_time(tip):
    raw = str(tip.get("commence_time") or tip.get("kickoff_utc") or "").strip()
    if not raw:
        return ""
    try:
        stamp=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return ""
        return stamp.astimezone(ZoneInfo("Europe/Zurich")).strftime("%d.%m.%Y · %H:%M Uhr")
    except (ValueError,TypeError,OverflowError):
        return ""

def render_regular(market, selection, tip, home, away, first, second, price, result=None):
    if market not in REGULAR:
        raise ValueError("No stadium master layout for this category")
    price=float(price)
    if not math.isfinite(price) or not 1<price<100:
        raise ValueError("Invalid observed single price")
    original=load_master()
    canvas=original.copy()
    # Keep original artwork; draw only data labels and transparent crests.
    _crest(canvas,first,(310,530))
    _crest(canvas,second,(812,530))
    dr=ImageDraw.Draw(canvas)
    _label(dr,(561,325),TITLES[market],660,50,GOLD)
    _label(dr,(561,530),"VS",110,52,GOLD)
    _label(dr,(310,716),home,470,35)
    _label(dr,(812,716),away,470,35)
    kickoff=_verified_time(tip)
    if kickoff:
        _label(dr,(561,773),kickoff,960,30,CYAN)
    _label(dr,(561,865),selection,925,44)
    _label(dr,(561,923),f"QUOTE  @{price:.2f}",925,43,GOLD)
    prob=tip.get("probability")
    if prob is not None and prob != "":
        from netrattler_btts_owner_original import _percent
        _label(dr,(561,1025),"MODELL  "+_percent(prob,strict=True),900,38,CYAN)
    league=str(tip.get("league") or "").strip()
    if league:
        _label(dr,(561,1090),league,920,31)
    marks=(result or {}).get("marks") or {}
    state={"win":"GEWONNEN","won":"GEWONNEN","loss":"VERLOREN","lost":"VERLOREN","void":"VOID","push":"PUSH"}.get(str(marks.get("0") or "").lower(),"OFFEN")
    _label(dr,(561,1215),"AUSWERTUNG: "+state,920,38,GOLD if state=="OFFEN" else WHITE)
    _label(dr,(561,1260),str((result or {}).get("ft") or ""),900,28)
    if ImageChops.difference(original.crop((0,0,1122,265)),canvas.crop((0,0,1122,265))).getbbox():
        raise AssertionError("Owner masthead pixels changed")
    out=BytesIO()
    canvas.save(out,format="PNG",optimize=True)
    return out.getvalue()
