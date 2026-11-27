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

MASTER = Path(__file__).resolve().parent / "assets/premium_master/netrattler_master_background_20261127.png"
DIGEST = "b240ae8aafd192a2ee4bd39c30add32e6bcccd7aa2110ea9bfb7e42d488cae3b"
DIMENSIONS = (1122, 1402)
VERSION = "master-background-20261127"
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
            draw.text(xy,value,font=f,anchor="mm",fill=color,stroke_width=3,stroke_fill=(3,13,26))
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
    """Regular single-market card on the pinned master background."""
    if market not in REGULAR:
        raise ValueError("No master layout for this category")
    price = float(price)
    if not math.isfinite(price) or not 1 < price < 100:
        raise ValueError("Invalid observed single price")
    load_master()  # pinned digest check
    import netrattler_master_cards as M
    prob = tip.get("probability")
    if prob is not None and prob != "":
        from netrattler_btts_owner_original import _percent
        prob = float(_percent(prob, strict=True).rstrip("%").replace(",", "."))
    else:
        prob = None
    marks = (result or {}).get("marks") or {}
    state = {"win": "GEWONNEN", "won": "GEWONNEN", "loss": "VERLOREN", "lost": "VERLOREN",
             "void": "VOID", "push": "PUSH"}.get(str(marks.get("0") or "").lower(), "OFFEN")
    kick = _verified_time(tip).replace(" Uhr", "")
    spec = dict(title=TITLES[market], tip=selection, odds=price, prob=prob, optional_prob=True,
                league=str(tip.get("league") or "").strip() or None,
                kickoff=kick or None, result=state, stats=[])
    return M.render_match(spec, home, away, first, second)
