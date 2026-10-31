"""Shared Premium Midnight arena, rendered locally without image downloads."""
from PIL import Image, ImageDraw

NAVY = '#071A3D'
PANEL = '#0A1B32'
TEAL = '#2EE6C5'


def midnight_arena(width, height):
    image = Image.new('RGB', (width, height), NAVY)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        draw.line((0,y,width,y), fill=(int(7-3*t),int(26-12*t),int(61-27*t)))
    # Roof trusses and curved spectator tiers frame the content.
    roof = int(min(height*.20, 210))
    for side in (-1,1):
        anchor = 0 if side == -1 else width
        for i in range(1,8):
            x = anchor - side*int(width*i/16)
            draw.line((anchor,0,x,roof), fill='#17334B',width=2)
        draw.line((anchor,roof, width//2, int(roof*.27)),fill='#28475C',width=2)
    for y in (int(roof*.7),roof,int(roof*1.36)):
        draw.arc((-width//5,-y,width*6//5,y*2),0,180,fill='#184558',width=3)
    draw.arc((-width//5,-roof,width*6//5,roof*2),0,180,fill='#249DA8',width=3)
    for x in range(30,width,75):
        cy = int(roof*.35 + abs(x-width/2)/width*roof*.4)
        draw.ellipse((x-2,cy-2,x+2,cy+2),fill='#94B6C7')
    # Restrained pitch and LED lines remain visible around opaque panels.
    floor = height-65
    draw.polygon([(0,height),(width*.3,floor),(width*.7,floor),(width,height)],fill='#082B35')
    draw.line((0,height-2,width*.3,floor,width*.7,floor,width,height-2),fill='#1B6770',width=2)
    return image
