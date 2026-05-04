#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the remaining sidebar category icons in the info_node baseline
style: thin outer ring, large inner symbol, gap to the ring for depth.

Run from the Intricate root:  python icons/gen_sidebar_categories.py

Icons produced
--------------
  text_node.ico      — Text   (four paragraph lines + end cursor)
  polaroid.ico   — Images (2x2 picture frames with mountain + sun)
  audio_group.ico    — Audio  (speaker cone + radiating arcs)
  tools_group.ico    — Tools  (wrench + hex nut)
"""

from PIL import Image, ImageDraw
import math, os

S   = 2048
cx  = cy = S // 2
C   = (225, 213, 198, 255)
RING_W = 12            # matches info_node baseline
MAX_EXTENT = 680       # clear gap to the ring (ring at 800)

# Script lives at tools/icon_pipeline/scripts/ now — go up 3 levels to
# repo root, then into icons/ for the output target.  Pre-2026-05-04
# the script was directly in icons/ and OUT was just dirname(__file__).
OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "icons"))


def _base():
    img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - 800, cy - 800, cx + 800, cy + 800],
                 outline=C, width=RING_W)
    return img, draw


def _save(img, name):
    path_ico = os.path.join(OUT, f'{name}.ico')
    out = img.resize((1024, 1024), Image.LANCZOS)
    out.save(os.path.join(OUT, f'{name}.png'))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    out.save(path_ico, format='ICO', sizes=[(s, s) for s in sizes])
    print(f'done  {path_ico}')


# ── 1. Text — four paragraph lines, last one half-width + cursor ────────────
img, draw = _base()

line_w = 56
lines_x_full  = (cx - 560, cx + 560)
lines_x_short = (cx - 560, cx + 180)
line_ys = [cy - 360, cy - 120, cy + 120, cy + 360]

for i, ly in enumerate(line_ys):
    x0, x1 = lines_x_short if i == 3 else lines_x_full
    draw.line([(x0, ly), (x1, ly)], fill=C, width=line_w)

# Blinking-cursor stub to the right of the short last line
cursor_x = lines_x_short[1] + 90
cursor_w = 28
cursor_half = 70
draw.line([(cursor_x, cy + 360 - cursor_half),
           (cursor_x, cy + 360 + cursor_half)],
          fill=C, width=cursor_w)

_save(img, 'text_node')


# ── 2. Images — fingertips holding a polaroid toward the sun ───────────────
#    Converged through two deductive rounds.  The "Images" icon depicts
#    the act of attention itself — a captured moment being lifted for
#    closer inspection, toward light.  Three elements:
#      (a) ambient halo behind the polaroid    — sun / ambient light
#      (b) the polaroid silhouette (tilted)    — the image-object
#      (c) two fingertips at the lower edge    — gesture of care
#    Hand gestures kept surfacing in the candidate lists; the polaroid
#    was the only rectangle the user didn't reject; the sun carries the
#    upward/onward register.  All three distilled into a single scene.
img, draw = _base()

# (a) Polaroid — large and tilted, dominant focal point.  No sun halo;
# the tilt + held gesture carries the "offered upward" narrative alone.
tilt = math.radians(-18)
ct, st = math.cos(tilt), math.sin(tilt)
body_w, body_h = 560, 640
body_cx, body_cy = cx + 60, cy - 90
hw, hh = body_w // 2, body_h // 2

def _rot(px, py):
    return (body_cx + int(px * ct - py * st),
            body_cy + int(px * st + py * ct))

corners = [_rot(-hw, -hh), _rot(hw, -hh), _rot(hw, hh), _rot(-hw, hh)]
stroke = 32
for i in range(4):
    draw.line([corners[i], corners[(i + 1) % 4]], fill=C, width=stroke)

# Inner separator — polaroid's characteristic bottom print-border.
sep_y_local = hh - 160
draw.line([_rot(-hw, sep_y_local), _rot(hw, sep_y_local)],
          fill=C, width=stroke)

# (b) Hand gesture — crossed thumb + index forming a heart pinch at
# the polaroid's lower-left corner.  Drawn as two thick bezier curves
# that sweep from off-frame into the corner and cross there, with a
# small negative space between them that reads as the heart-shape
# point.
def _bezier(p0, p1, p2, p3, steps=80):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3 * p3[1]
        pts.append((int(x), int(y)))
    return pts

# Lower-left corner of the polaroid in scene coords
corner_xy = _rot(-hw, hh)

# Thumb — curves from off-frame below-left UP and into the corner,
# ending slightly INSIDE the polaroid body so it reads as pressing
# against the corner from below.
thumb_pts = _bezier(
    (cx - 500, cy + 620),
    (cx - 400, cy + 460),
    (cx - 290, cy + 340),
    (corner_xy[0] + 60, corner_xy[1] - 30),   # crosses slightly into the corner
)
draw.line(thumb_pts, fill=C, width=130, joint='curve')

# Fingertips visible ABOVE the polaroid's top-left edge — the hand
# wraps around behind the photo, fingertips curling over the top.
# Three visible tips, crossing the top edge like fingers pinching.
def _tip_on_edge(px_local, py_local, w, lean_deg=0):
    """Draw a fingertip dome straddling the polaroid's top edge at a
    local offset (px_local, py_local) from body center.  lean_deg
    rotates the dome's flat side to match the polaroid's tilt."""
    px, py = _rot(px_local, py_local)
    r = w // 2
    # Rotate the pieslice by polaroid tilt so the dome sits flush on
    # the tilted top edge.
    tilt_deg = math.degrees(tilt)
    start = 180 - tilt_deg + lean_deg
    end   = 360 - tilt_deg + lean_deg
    draw.pieslice([px - r, py - r, px + r, py + r],
                  start=start, end=end, fill=C)

# Three fingertip domes along the polaroid's TOP edge (near the left
# side).  Base y = -hh positions each at the top edge.
_tip_on_edge(-hw + 120, -hh, 150)   # index — biggest, closest to corner
_tip_on_edge(-hw + 280, -hh, 130)   # middle
_tip_on_edge(-hw + 420, -hh, 100)   # ring finger hint

_save(img, 'polaroid')


# ── 3. Audio — speaker cone + three radiating arcs ──────────────────────────
#    Speaker body is one continuous filled silhouette (mouth + cone) so
#    the shape reads as a single object, not two strokes of different
#    weight.
img, draw = _base()

mouth_left_x  = cx - 540
mouth_right_x = cx - 360
mouth_top     = cy - 140
mouth_bottom  = cy + 140
cone_front_x      = cx - 60
cone_front_top    = cy - 340
cone_front_bottom = cy + 340

draw.polygon(
    [(mouth_left_x, mouth_top),
     (mouth_right_x, mouth_top),
     (cone_front_x, cone_front_top),
     (cone_front_x, cone_front_bottom),
     (mouth_right_x, mouth_bottom),
     (mouth_left_x, mouth_bottom)],
    fill=C,
)

# Three radiating arcs — stacked right of the cone, growing wider
arc_stroke = 46
for i, (r, open_deg) in enumerate([(180, 80), (320, 70), (460, 62)]):
    bbox = [cx + 60 - r, cy - r, cx + 60 + r, cy + r]
    draw.arc(bbox, start=-open_deg / 2, end=open_deg / 2,
             fill=C, width=arc_stroke)

_save(img, 'audio_group')


# ── 4. Tools — single wrench, diagonal, open C-head ─────────────────────────
#    Simpler than wrench+nut: one unified glyph reads cleaner at sidebar
#    size.  Diagonal axis from bottom-left to upper-right; the open C at
#    the upper end is carved by over-drawing transparent pixels, since
#    Pillow has no native "arc as closed ring with a slot" primitive.
img, draw = _base()

handle_stroke = 90
handle_start = (cx - 500, cy + 500)
handle_end   = (cx + 200, cy - 200)
draw.line([handle_start, handle_end], fill=C, width=handle_stroke)

# Wrench open C-head at the upper end
head_cx, head_cy = cx + 320, cy - 320
head_r = 240
ring_stroke = 80
draw.ellipse([head_cx - head_r, head_cy - head_r,
              head_cx + head_r, head_cy + head_r],
             outline=C, width=ring_stroke)

# Carve the opening by drawing a transparent pie wedge on top.  The
# opening points up and to the right (away from the handle).
opening_deg = 70
opening_center_deg = -45                # up-right
half = math.radians(opening_deg / 2)
c0 = math.radians(opening_center_deg) - half
c1 = math.radians(opening_center_deg) + half
outer = head_r + ring_stroke + 10
wedge = [
    (head_cx, head_cy),
    (head_cx + outer * math.cos(c0), head_cy + outer * math.sin(c0)),
    (head_cx + outer * math.cos((c0 + c1) / 2),
     head_cy + outer * math.sin((c0 + c1) / 2)),
    (head_cx + outer * math.cos(c1), head_cy + outer * math.sin(c1)),
]
draw.polygon(wedge, fill=(0, 0, 0, 0))

_save(img, 'tools_group')

print('all done')
