"""One-time creation of a data-free static plate from the supplied owner image.

IMPORTANT: This does *not* claim to reverse engineer the underlying pixels.
The user-supplied original is never overwritten; only explicitly designated
variable fields are reconstructed in a separate image. Dynamic content is
composed on the resulting static plate, with no old text underneath.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'last_minute_user_original.png'
TARGET=HERE/'last_minute_clean_plate.png'

# Regions were measured against the owner's 512x512 source artwork.
# Do not clear surrounding frame/branding or the permanent market names.
REGIONS={
 'league':(160,80,380,94),
 'live_badge':(239,105,279,121),
 'minute':(240,124,274,147),
 'score':(218,156,295,189),
 'team_home':(61,173,183,191),
 'team_away':(332,173,476,191),
 'home_xg':(48,220,173,239),
 'center_xg':(216,221,307,238),
 'away_xg':(355,220,471,239),
 'winrate_l':(153,340,228,352),
 'winrate_r':(413,340,496,352),
 'next_team':(205,441,344,466),
 'prob_over':(395,407,470,429),
 'prob_next':(396,448,476,472),
}
# Single numerical value boxes + full stat bars: do not keep leftover example
# length of the cyan/orange bars. Column labels in the middle remain untouched.
STAT_Y=[253,270,286,303,320]
for i,y in enumerate(STAT_Y):
    REGIONS['stat_left_'+str(i)]=(18,y-7,53,y+7)
    REGIONS['stat_right_'+str(i)]=(458,y-7,493,y+7)
    REGIONS['bar_left_'+str(i)]=(62,y-7,156,y+7)
    REGIONS['bar_right_'+str(i)]=(358,y-7,456,y+7)

# The two example crests must be removed at plate-build time, not patched
# with invisible historical art under every new team's authentic logo.
CRESTS=((52,94,140,172),(376,94,466,172))

def make_plate(source=SOURCE,target=TARGET):
    im=Image.open(source).convert('RGB')
    if im.size!=(512,512):
        raise ValueError('Actual original reference dimensions changed')
    original=np.array(im)
    # Slightly extend the inpaint mask around old text antialiasing, but
    # keep identity-bearing branding and the visual gold/cyan outlines.
    mask=np.zeros((512,512),dtype=np.uint8)
    for (x0,y0,x1,y1) in REGIONS.values():
        mask[y0:y1,x0:x1]=255
    for (x0,y0,x1,y1) in CRESTS:
        mask[y0:y1,x0:x1]=255
    # Reconstruct small variable-value regions once in the background master.
    cleaned=cv2.inpaint(original,mask,3,cv2.INPAINT_TELEA)
    result=Image.fromarray(cleaned)
    d=ImageDraw.Draw(result)
    # Neutral reconstructive fills avoid inpainting ghost numbers. These
    # changes belong to the static plate generation, NEVER the live renderer.
    palette={
        'league':(1,23,25),'live_badge':(175,15,11),
        'minute':(2,7,11),'score':(1,8,12),
        'team_home':(0,35,29),'team_away':(0,35,29),
        'home_xg':(1,38,32),'center_xg':(0,31,27),
        'away_xg':(1,38,32),'winrate_l':(0,25,22),
        'winrate_r':(0,25,22),'next_team':(1,41,41),
        'prob_over':(2,27,11),'prob_next':(2,27,12),
    }
    for key,(x0,y0,x1,y1) in REGIONS.items():
        if key.startswith('stat_'):
            fill=(1,17,23)
        elif key.startswith('bar_'):
            fill=(1,21,25)
        else:
            fill=palette[key]
        d.rectangle((x0,y0,x1-1,y1-1),fill=fill)

    # Remove the *shield-shaped* sample backgrounds as well as sample logos.
    # Plain CV inpainting over those 90px blocks propagated the old bright
    # gold-and-white shield colours into metallic X/triangle artifacts.
    # Restore the crowd/stadium from adjacent, unobstructed OWNER pixels ONCE
    # in this derived static plate. Runtime draws no fake backplates.
    for (x0,y0,x1,y1),donor_box in zip(
            CRESTS,((141,99,198,172),(317,99,374,172))):
        width,height=x1-x0,y1-y0
        real_stadium=im.crop(donor_box).resize(
            (width,height),Image.Resampling.BICUBIC)
        feather=Image.new('L',(width,height),0)
        md=ImageDraw.Draw(feather)
        md.rounded_rectangle((2,2,width-3,height-3),radius=10,fill=255)
        feather=feather.filter(ImageFilter.GaussianBlur(2.5))
        result.paste(real_stadium,(x0,y0),feather)
    result.save(target,format='PNG',optimize=True)
    # Produce exact static-pixel proof: only sanctioned regions differ.
    new=np.array(result)
    permitted=cv2.dilate(mask,np.ones((3,3),np.uint8),iterations=1)>0
    changed=np.any(original!=new,axis=2)
    if not np.all((~changed)|permitted):
        raise AssertionError('Static owner artwork changed outside dynamic slots')
    return {'changed_pixels':int(changed.sum()),'total_pixels':512*512,
            'unchanged_pct':round(100*(1-changed.mean()),2)}

if __name__=='__main__':
    print(make_plate())