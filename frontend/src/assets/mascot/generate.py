"""Generates the Clutch / Mother Hen SVGs in this folder. Edit the colors or poses, then run it again."""
from pathlib import Path
OUT = Path(__file__).resolve().parent  # run: python generate.py

INK = "#5B3A29"; CREAM = "#FFF8EC"; WING = "#F4E3C3"; BELLY = "#FFFDF8"
COMB = "#EF5A5A"; BEAK = "#F7A72B"; BLUSH = "#F9A8B4"; SHELL = "#FBEFD5"
SPECK = "#E8CC98"; CHICK = "#FFD54A"; CHICK_SH = "#F5BE2E"; SPARK = "#FFC83D"
SW = 6  # outline width

def svg(vb, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="{title}">'
            f'<title>{title}</title>{body}</svg>\n')

def outlined(shapes, fill):
    """Draw shapes with a merged outline: thick ink strokes underneath, fills on top."""
    under = "".join(s.format(f'fill="{INK}" stroke="{INK}" stroke-width="{SW*2}" stroke-linejoin="round"') for s in shapes)
    over = "".join(s.format(f'fill="{fill}"') for s in shapes)
    return under + over

def eye(x, y, look=(0, 0)):
    dx, dy = look
    return (f'<circle cx="{x}" cy="{y}" r="7" fill="{INK}"/>'
            f'<circle cx="{x+2+dx}" cy="{y-2.5+dy}" r="2.6" fill="#fff"/>')

def happy_eye(x, y):
    return f'<path d="M{x-8} {y+3} Q{x} {y-8} {x+8} {y+3}" fill="none" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>'

def face(eyes="open", look=(0, 0), mouth=False):
    e = (happy_eye(101, 86) + happy_eye(139, 86)) if eyes == "happy" else (eye(101, 86, look) + eye(139, 86, look))
    blush = (f'<ellipse cx="88" cy="104" rx="10" ry="6" fill="{BLUSH}" opacity=".75"/>'
             f'<ellipse cx="152" cy="104" rx="10" ry="6" fill="{BLUSH}" opacity=".75"/>')
    wattle = f'<path d="M114 112 Q120 132 126 112 Z" fill="{COMB}" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>'
    beak = (f'<path d="M108 102 Q120 92 132 102 Q120 114 108 102 Z" fill="{BEAK}" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>'
            f'<path d="M110 102 H130" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>')
    if mouth:  # open, cheerful beak
        beak = (f'<path d="M107 100 Q120 90 133 100 Z" fill="{BEAK}" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>'
                f'<path d="M110 103 Q120 116 130 103 Z" fill="{BEAK}" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>')
    return e + blush + wattle + beak

def comb():
    return outlined(['<circle cx="104" cy="44" r="13" {}/>', '<circle cx="120" cy="34" r="15" {}/>',
                     '<circle cx="136" cy="44" r="13" {}/>'], COMB)

def wing(side, pose="rest"):
    # Wings are teardrops attached at the shoulder; pose rotates them.
    if side == "L":
        x, rot = 66, {"rest": 18, "up": 115, "chin": -95}[pose]
    else:
        x, rot = 174, {"rest": -18, "up": -115, "chin": 95}[pose]
    cy = 150
    d = (f'<path d="M{x} {cy-28} C {x+26} {cy-20} {x+24} {cy+20} {x} {cy+34} '
         f'C {x-24} {cy+20} {x-26} {cy-20} {x} {cy-28} Z" '
         f'transform="rotate({rot} {x} {cy-24})" {{}}/>')
    feathers = (f'<path d="M{x-8} {cy+8} Q{x} {cy+16} {x+8} {cy+8}" fill="none" stroke="{INK}" '
                f'stroke-width="3" stroke-linecap="round" opacity=".45" transform="rotate({rot} {x} {cy-24})"/>')
    return outlined([d], WING) + feathers

def hen(eyes="open", look=(0, 0), left="rest", right="rest", mouth=False, extra_back="", extra_front="", glasses=False):
    shadow = '<ellipse cx="120" cy="226" rx="66" ry="8" fill="#000" opacity=".08"/>'
    feet = "".join(
        f'<path d="M{x} 206 v12 M{x} 218 l-8 5 M{x} 218 l8 5 M{x} 218 v7" stroke="{BEAK}" stroke-width="6" '
        f'stroke-linecap="round" fill="none"/>' for x in (100, 140))
    tail = outlined(['<path d="M170 120 Q186 82 204 74 Q200 102 186 128 Z" {}/>',
                     '<path d="M176 128 Q200 104 216 102 Q206 128 188 140 Z" {}/>'], WING)
    body = outlined(['<ellipse cx="120" cy="150" rx="76" ry="62" {}/>', '<circle cx="120" cy="90" r="52" {}/>'], CREAM)
    belly = f'<ellipse cx="120" cy="166" rx="46" ry="34" fill="{BELLY}"/>'
    belly_marks = "".join(f'<path d="M{x-6} {y} q6 6 12 0" fill="none" stroke="{WING}" stroke-width="3" stroke-linecap="round"/>'
                          for x, y in ((106, 158), (134, 158), (120, 174)))
    specs = ""
    if glasses:
        specs = (f'<g fill="none" stroke="{INK}" stroke-width="3.5"><circle cx="101" cy="86" r="13"/>'
                 f'<circle cx="139" cy="86" r="13"/><path d="M114 84 Q120 80 126 84"/></g>')
    # Back wing drawn under body when resting; raised wings drawn on top so they read.
    parts = [shadow, extra_back, feet, tail]
    under = [w for w, p in ((wing("L", left), left), (wing("R", right), right)) if p == "rest"]
    over = [w for w, p in ((wing("L", left), left), (wing("R", right), right)) if p != "rest"]
    parts += [comb(), body, belly] + under + [face(eyes, look, mouth), specs] + over + [extra_front]
    return "".join(parts)

def sparkle(x, y, s=1.0, color=SPARK):
    return (f'<path d="M{x} {y-12*s} Q{x+2*s} {y-2*s} {x+12*s} {y} Q{x+2*s} {y+2*s} {x} {y+12*s} '
            f'Q{x-2*s} {y+2*s} {x-12*s} {y} Q{x-2*s} {y-2*s} {x} {y-12*s} Z" fill="{color}"/>')

def heart(x, y, s=1.0):
    return (f'<path d="M{x} {y+8*s} C{x-14*s} {y-2*s} {x-8*s} {y-14*s} {x} {y-6*s} '
            f'C{x+8*s} {y-14*s} {x+14*s} {y-2*s} {x} {y+8*s} Z" fill="{COMB}"/>')

thought = (f'<circle cx="182" cy="52" r="5" fill="{WING}" stroke="{INK}" stroke-width="3"/>'
           f'<circle cx="198" cy="34" r="8" fill="{WING}" stroke="{INK}" stroke-width="3"/>'
           f'<circle cx="220" cy="12" r="11" fill="{WING}" stroke="{INK}" stroke-width="3"/>')

VB = "0 0 240 240"
assets = {
    "hen-default": svg(VB, hen(), "Mother Hen"),
    "hen-thinking": svg(VB, hen(look=(2, -3), right="chin", glasses=True, extra_front=thought), "Mother Hen thinking"),
    "hen-happy": svg(VB, hen(eyes="happy", left="up", right="up", mouth=True,
                             extra_front=sparkle(30, 60, 1.1) + sparkle(212, 70, .9) + sparkle(46, 24, .6)), "Mother Hen cheering"),
    "hen-wave": svg(VB, hen(right="up", extra_front=heart(214, 40, 1.1)), "Mother Hen waving"),
    "hen-proud": svg(VB, hen(eyes="happy", extra_front=heart(40, 50, .9) + heart(204, 46, .7)), "Mother Hen proud"),
}

# Avatar: head only, cropped in a circle, for chat bubbles.
avatar_body = (f'<clipPath id="c"><circle cx="120" cy="120" r="116"/></clipPath>'
               f'<circle cx="120" cy="120" r="116" fill="#FFE9C7"/>'
               f'<g clip-path="url(#c)" transform="translate(0 28)">{comb()}'
               + outlined(['<circle cx="120" cy="96" r="60" {}/>', '<ellipse cx="120" cy="190" rx="90" ry="60" {}/>'], CREAM)
               + face() + '</g>'
               f'<circle cx="120" cy="120" r="116" fill="none" stroke="{INK}" stroke-width="6"/>')
assets["hen-avatar"] = svg(VB, avatar_body, "Mother Hen")

# Favicon: simplified head, bolder, readable at 16px.
fav = (f'<g transform="translate(-19.6 -4.6) scale(.43)">{comb()}' +
       outlined(['<circle cx="120" cy="100" r="50" {}/>'], CREAM) +
       eye(101, 96).replace('r="7"', 'r="9"') + eye(139, 96).replace('r="7"', 'r="9"') +
       f'<path d="M106 112 Q120 100 134 112 Q120 126 106 112 Z" fill="{BEAK}" stroke="{INK}" stroke-width="4"/></g>')
assets["favicon"] = svg("0 0 64 64", fav, "Clutch")

# ---------- eggs: mastery stages 0-4 ----------
EGG = "M60 10 C 94 10 112 62 112 90 C 112 120 90 136 60 136 C 30 136 8 120 8 90 C 8 62 26 10 60 10 Z"
def egg_shell(clip=None):
    specks = "".join(f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{r*.8}" fill="{SPECK}"/>'
                     for x, y, r in ((40, 60, 5), (78, 48, 4), (86, 92, 6), (34, 104, 4), (62, 118, 3.5), (58, 78, 3)))
    shine = f'<path d="M34 50 Q40 32 52 24" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" opacity=".8"/>'
    return f'<path d="{EGG}" fill="{SHELL}" stroke="{INK}" stroke-width="5"/>{specks}{shine}'

def chick(cx, cy, r=26, happy=False):
    eyes = (f'<path d="M{cx-12} {cy-1} q5 -7 10 0 M{cx+2} {cy-1} q5 -7 10 0" fill="none" stroke="{INK}" stroke-width="3.5" stroke-linecap="round"/>'
            if happy else f'<circle cx="{cx-8}" cy="{cy-3}" r="4" fill="{INK}"/><circle cx="{cx+8}" cy="{cy-3}" r="4" fill="{INK}"/>'
                          f'<circle cx="{cx-6.5}" cy="{cy-4.5}" r="1.4" fill="#fff"/><circle cx="{cx+9.5}" cy="{cy-4.5}" r="1.4" fill="#fff"/>')
    return (f'<path d="M{cx-3} {cy-r+2} q-2 -12 6 -14 M{cx+2} {cy-r+2} q4 -10 10 -8" fill="none" stroke="{INK}" stroke-width="3.5" stroke-linecap="round"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{CHICK}" stroke="{INK}" stroke-width="5"/>'
            f'<ellipse cx="{cx-14}" cy="{cy+8}" rx="6" ry="4" fill="{BLUSH}" opacity=".8"/>'
            f'<ellipse cx="{cx+14}" cy="{cy+8}" rx="6" ry="4" fill="{BLUSH}" opacity=".8"/>'
            + eyes +
            f'<path d="M{cx-6} {cy+5} L{cx+6} {cy+5} L{cx} {cy+12} Z" fill="{BEAK}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>')

CRACK_EDGE = "8 84 22 74 32 86 44 72 56 86 68 72 80 86 92 72 104 84 112 82"
def crack(points, w=4):
    return f'<polyline points="{points}" fill="none" stroke="{INK}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"/>'

EVB = "0 0 120 140"
egg_shadow = '<ellipse cx="60" cy="136" rx="40" ry="5" fill="#000" opacity=".08"/>'
assets["egg-0"] = svg(EVB, egg_shadow + egg_shell(), "Egg: not started")
assets["egg-1"] = svg(EVB, egg_shadow + egg_shell() + crack("58 12 52 26 62 34 54 46"), "Egg: a little progress")
assets["egg-2"] = svg(EVB, egg_shadow + egg_shell() + crack("14 66 28 58 36 70 50 56 60 68 72 56 84 70 96 58 106 66")
                      + crack("60 68 56 82 64 90", 3.5), "Egg: halfway")
# Stage 3: top of shell lifted, chick peeking out.
bottom_half = (f'<clipPath id="b"><polygon points="0 140 0 84 {CRACK_EDGE} 120 84 120 140"/></clipPath>'
               f'<g clip-path="url(#b)">{egg_shell()}</g>'
               f'<polyline points="{CRACK_EDGE}" fill="none" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>')
cap_shape = f'<path d="M14 62 C 22 26 40 10 60 10 C 80 10 98 26 106 62 L 92 56 80 66 68 54 56 66 44 54 32 66 Z" fill="{SHELL}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
assets["egg-3"] = svg(EVB, egg_shadow + chick(60, 76, 26) + bottom_half
                      + f'<g transform="rotate(-18 60 40) translate(-6 -22)">{cap_shape}</g>', "Egg: almost hatched")
# Stage 4: chick out, standing in its shell, cap off to the side.
assets["egg-4"] = svg(EVB, egg_shadow + chick(60, 66, 30, happy=True)
                      + '<g transform="translate(0 16)">' + bottom_half.replace('id="b"', 'id="b2"').replace("url(#b)", "url(#b2)") + '</g>'
                      + sparkle(16, 26, .7) + sparkle(104, 20, .55), "Egg: hatched! Mastered")

# ---------- logo ----------
logo = (f'<g transform="translate(4 4) scale(.5)">{hen()}</g>'
        f'<text x="132" y="84" font-family="Fredoka, Nunito, \'Arial Rounded MT Bold\', ui-rounded, system-ui, sans-serif" '
        f'font-size="58" font-weight="700" fill="{INK}" letter-spacing="1">Clutch</text>'
        f'<text x="134" y="108" font-family="Nunito, ui-rounded, system-ui, sans-serif" font-size="15" fill="#8A6A55">study with Mother Hen</text>'
)
assets["logo"] = svg("0 0 370 128", logo, "Clutch")

# ---------- topic badge (earned by passing a mastery quiz) ----------
import math as _m
GOLD = "#FFC83D"; GOLD_DK = "#F0A81E"; RIBBON = COMB; RIBBON_DK = "#D64545"

def rosette(cx, cy, r_out, r_in, n, fill):
    pts = []
    for i in range(n * 2):
        a = _m.pi * i / n - _m.pi / 2
        r = r_out if i % 2 == 0 else r_in
        pts.append(f"{cx + r * _m.cos(a):.1f},{cy + r * _m.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'

def ribbons(color, dark):
    return (f'<path d="M78 130 L58 206 L76 196 L88 214 L104 140 Z" fill="{color}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
            f'<path d="M142 130 L162 206 L144 196 L132 214 L116 140 Z" fill="{color}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
            f'<path d="M84 150 L72 196" stroke="{dark}" stroke-width="4" stroke-linecap="round"/>'
            f'<path d="M136 150 L148 196" stroke="{dark}" stroke-width="4" stroke-linecap="round"/>')

GOLD_EGG = "M110 62 C 128 62 138 90 138 104 C 138 120 126 130 110 130 C 94 130 82 120 82 104 C 82 90 92 62 110 62 Z"
badge_body = (ribbons(RIBBON, RIBBON_DK)
              + rosette(110, 96, 78, 66, 16, GOLD)
              + f'<circle cx="110" cy="96" r="54" fill="{GOLD_DK}" stroke="{INK}" stroke-width="4"/>'
              + f'<circle cx="110" cy="96" r="44" fill="{CREAM}" stroke="{INK}" stroke-width="4"/>'
              + f'<g transform="translate(0 -4)"><path d="{GOLD_EGG}" fill="{GOLD}" stroke="{INK}" stroke-width="5"/>'
              + f'<path d="M95 84 Q99 74 106 70" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" opacity=".85"/>'
              + f'<path d="M97 101 L106 110 L124 90" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></g>'
              + sparkle(186, 34, .8, "#fff").replace('fill="#fff"', f'fill="{GOLD}" stroke="{INK}" stroke-width="2.5"')
              + sparkle(34, 150, .6, GOLD))
assets["badge"] = svg("0 0 220 220", badge_body, "Topic badge")

GREY = "#E4DED6"; GREY_DK = "#CFC6BA"
locked_body = (ribbons(GREY, GREY_DK)
               + rosette(110, 96, 78, 66, 16, GREY)
               + f'<circle cx="110" cy="96" r="54" fill="{GREY_DK}" stroke="{INK}" stroke-width="4"/>'
               + f'<circle cx="110" cy="96" r="44" fill="#F6F2EC" stroke="{INK}" stroke-width="4"/>'
               + f'<g transform="translate(0 -4)"><path d="{GOLD_EGG}" fill="{GREY}" stroke="{INK}" stroke-width="5" stroke-dasharray="10 7"/></g>'
               + f'<text x="110" y="112" text-anchor="middle" font-family="Nunito, ui-rounded, system-ui, sans-serif" font-size="40" font-weight="800" fill="{INK}" opacity=".55">?</text>')
assets["badge-locked"] = svg("0 0 220 220", f'<g opacity=".9">{locked_body}</g>', "Badge not earned yet")

for name, text in assets.items():
    (OUT / f"{name}.svg").write_text(text)
print(sorted(assets))
