"""Gewinner-Uebersicht im NETRATTLER-Stil: beste Treffer der letzten Tage + ehrliche Gesamtbilanz."""
import io
from PIL import Image, ImageDraw, ImageFont

FB = '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'


def _font(n):
    try:
        return ImageFont.truetype(FB, n)
    except OSError:
        return ImageFont.load_default(size=n)


def render_recap(wins, days, record):
    """wins: [{date,match,t,odds,market}], record: {'n','w','units'} ueber ALLE abgerechneten Tipps."""
    from netrattler_card_theme import midnight_arena
    cols, tw, th, gap = 3, 360, 150, 20
    rows = max(1, -(-len(wins) // cols))
    h = 260 + rows * (th + gap) + 150
    im = midnight_arena(1200, h)
    d = ImageDraw.Draw(im)

    def center(t, x, y, n, c='#ffffff'):
        f = _font(n); d.text((x - d.textlength(str(t), font=f) / 2, y), str(t), font=f, fill=c)

    def fit(t, n, w):
        t = str(t)
        while t and d.textlength(t, font=_font(n)) > w:
            t = t[:-2].rstrip() + '…'
        return t

    center('NETRATTLER', 600, 22, 64)
    center(f'BESTE TREFFER · LETZTE {days} TAGE', 600, 105, 34, '#ffd84a')
    for i, w in enumerate(wins):
        x = 30 + (i % cols) * (tw + gap // 2 + 0) + (i % cols) * 0
        x = 30 + (i % cols) * (tw + 25)
        y = 190 + (i // cols) * (th + gap)
        d.rounded_rectangle((x, y, x + tw, y + th), radius=14, fill='#0A1B32', outline='#2EE6C5', width=2)
        d.text((x + 14, y + 10), fit(w['t'], 26, tw - 130), font=_font(26), fill='#ffffff')
        d.text((x + 14, y + 48), fit(w['match'], 19, tw - 28), font=_font(19), fill='#d4ecff')
        d.text((x + 14, y + 78), f"{w['market']} · {w['date'][5:]}", font=_font(16), fill='#a6c4dc')
        d.text((x + tw - 100, y + 12), f"@ {float(w['odds']):.2f}", font=_font(28), fill='#2EE6C5')
        d.text((x + 14, y + 108), '✔ GEWONNEN' if False else 'GEWONNEN', font=_font(22), fill='#2EE6C5')
    y = 190 + rows * (th + gap)
    sign = '+' if record['units'] >= 0 else ''
    center(f"Gesamtbilanz {days} Tage: {record['w']}/{record['n']} Treffer · {sign}{record['units']:.1f} Units (Einheitseinsatz)", 600, y + 20, 25, '#ffd84a')
    center('Alle abgerechneten Tipps zaehlen, nicht nur die Gewinner.', 600, y + 62, 20, '#a6c4dc')
    out = io.BytesIO(); im.save(out, format='PNG', optimize=True); return out.getvalue()
