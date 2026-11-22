"""NETRATTLER: offline PNG->Telegram chat simulation across all 16 markets.

Crucial separation:
- A TECHNICAL SVG that renders is not an approved user ORIGINAL image.
- An original screenshot with runtime opaque patches is NOT clean/approved.
- This program never calls a network endpoint or publishes a Telegram photo.
- Every card gets an actual-chat-layout mock with an edited/time label
  exclusively over a separate blank area, not on match/player/settlement data.

Outputs a machine-readable release-readiness report instead of mislabeling
synthetic previews as real bets. Hardtest passes only when ALL 16 technical
families render and production publication stays fail-closed.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from netrattler_premium_verified_cards import CATEGORIES
from netrattler_telegram_safe_zone import append_safe_margin, assert_safe_margin

ROOT=Path("sandbox-qa")
DEST=Path("sandbox-telegram-qa")
DEST.mkdir(exist_ok=True,parents=True)
technical={p.name.split("_SANDBOX_ONLY")[0]:p for p in ROOT.glob("*_SANDBOX_ONLY.png")}
missing=sorted(set(CATEGORIES)-set(technical))
if missing:
    raise SystemExit("FAIL: not all 16 technical card previews were rendered: "+", ".join(missing))
assert len(CATEGORIES)==16

# The only independent owner references on disk are not 16 approved masters.
# Keep this distinction visible in every exported manifest and preview.
reference={
    "builder":"BUILDER_4 original screenshot + source WebP (NOT CLEAN)",
    "goal":"GOAL HUNTER original screenshot + WebP (NOT CLEAN)",
    "corner":"CORNER SNIPER original WebP (NOT CLEAN)",
    "btts":"BTTS user-original PNG (reference, image still blocked in live workflow)",
    "combo":"COMBO 7/9 owner-original PNGs (variants are derived, not new originals)",
}
default_status="BLOCKED_TECHNICAL_SVG_NOT_APPROVED_OWNER_IMAGE"
results={}

try:
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",11)
    title_font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",13)
except OSError:
    font=ImageFont.load_default()
    title_font=font

def preview(name,original_bytes,source,approval_status):
    # Only a parsed real PNG is accepted. Both original input and the appended
    # scanline-only metadata gutter are compared pixel-exact offline.
    padded=append_safe_margin(original_bytes)
    assert_safe_margin(original_bytes,padded)
    with Image.open(io.BytesIO(original_bytes)) as im:
        body=im.convert("RGB")
    with Image.open(io.BytesIO(padded)) as im:
        poster=im.convert("RGB")
    x0,y0,w=18,80,354
    scale=w/poster.width
    scaled_h=round(poster.height*scale)
    original_h=round(body.height*scale)
    canvas=Image.new("RGB",(390,scaled_h+150),(18,27,43))
    d=ImageDraw.Draw(canvas)
    d.rectangle((0,0,390,68),fill=(29,44,67))
    d.text((20,24),"NETRATTLER  ·  SANDBOX",font=title_font,fill=(247,247,252))
    canvas.paste(poster.resize((w,scaled_h),Image.Resampling.LANCZOS),(x0,y0))
    d=ImageDraw.Draw(canvas)
    clock_top=y0+scaled_h-26
    assert clock_top>=y0+original_h+6,(
        name,"Telegram's clock has covered player/card/settlement area"
    )
    d.rounded_rectangle((x0+w-127,clock_top,x0+w-7,clock_top+21),
                        radius=6,fill=(10,22,32))
    d.text((x0+w-120,clock_top+4),"bearbeitet 23:01",
           font=font,fill=(240,245,254))
    d.text((18,y0+scaled_h+15),"SIMULATION · KEIN TELEGRAM-VERSAND",
           font=font,fill=(245,209,108))
    dest=DEST/("telegram_"+name+".png")
    canvas.save(dest,optimize=True)
    results[name]={
        "technical_sandbox":"PASS",
        "source_kind":source,
        "production_original_approval":approval_status,
        "production_send":False,
        "telegram_overlay_hits_original_art":False,
        "preview":str(dest),
        "poster_size":list(poster.size),
    }

for category,path in sorted(technical.items()):
    data=path.read_bytes()
    preview(category,data,"TECHNICAL_BLANK_SVG",default_status)

# Actual owner-reference routes, separately from technical SVGs.
# Fixtures contain invented teams/odds ONLY for disconnected visual QA.
from test_netrattler_btts_owner_original import OwnerBttsImageTests
from test_netrattler_combo_owner_original import render as combo_owner

preview("owner_btts",OwnerBttsImageTests().draw(),"USER_ORIGINAL_PNG",
        "BLOCKED_UNTIL_USER_ORIGINAL_VISUAL_ACCEPTANCE")
for n in (7,9):
    preview(f"owner_combo_{n}",combo_owner(n),"USER_ORIGINAL_PNG",
            "BLOCKED_UNTIL_VISUAL_CLEAN_SOURCE_AND_APPROVAL")

# Generated original Builder 2-7 and Goal Hunter previews are also checked,
# but are NOT promoted to approved cards because runtime screenshot paint
# operations still exist in the production code.
for item in sorted(Path("visual_review_previews").glob("TEST_ONLY_*.png")):
    with Image.open(item) as image:
        sample=image.convert("RGB")
    buf=io.BytesIO()
    sample.save(buf,"PNG")
    preview(item.stem,buf.getvalue(),"DERIVED_USER_ORIGINAL_WEBP",
            "BLOCKED_SOURCE_HAS_RUNTIME_OVERPAINT")

# Fail closed: production workflow must not be re-enabled by a green mock.
main=Path(".github/workflows/btts_tips.yml").read_text(encoding="utf-8")
assert "if: ${{ false }}" in main, "Unsafe LIVE tips resumed without original-art acceptance"
assert 'NETRATTLER_BLOCK_OVERPAINTED_MASTERS: "1"' in main
report={
    "date":"2026-11-22",
    "sandbox_only":True,
    "telegram_real_app_pixel_match":"NOT_VERIFIED",
    "technical_families_rendered":16,
    "all_16_owner_artwork_approved":False,
    "missing_independent_originals":sorted(set(CATEGORIES)-set(reference)),
    "individual_results":results,
}
(DEST/"report.json").write_text(
    json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"
)
assert len(results)>=19, "Missing owner screenshot preview families"
print("NETRATTLER_TELEGRAM_SANDBOX_16_CATEGORIES_AND_OWNER_REFERENCES_PASS",
      len(results))
print("PRODUCTION_BLOCKED_MISSING_APPROVED_ORIGINALS",
      len(report["missing_independent_originals"]))
print("NO_NETWORK_NO_TELEGRAM_NO_REAL_TIPS")
