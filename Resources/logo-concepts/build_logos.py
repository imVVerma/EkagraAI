#!/usr/bin/env python3
"""Ekagra logo concepts — geometry, SVG output, and PNG proofs.

Every asset is emitted from the shape definitions below, so a change in
geometry propagates to all variants at once. The vocabulary is deliberately
tiny (rect, circle, ring, line) so the SVGs stay a few hundred bytes and can be
hand-edited afterwards.

Marks live on a 64x64 grid. Concept-specific accents:

  concept 1  concentric focus, a broken outer ring, one progress bead
  concept 2  a geometric E whose bars converge on a point on its axis
  concept 3  three paths merging into one point, then one path onward

Run:  python3 build_logos.py
"""

import math
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Palette — taken from frontend/styles.css so the marks sit inside the
# existing visual language rather than beside it.
# ---------------------------------------------------------------------------
ACCENT      = "#1f4e5f"   # --accent, deep teal: primary mark colour
ACCENT_LINE = "#c3d8de"
PASS        = "#2f6b4f"   # --pass, green: the focused point / achievement
PASS_LIGHT  = "#8ec7a8"   # the same accent, lifted for dark backgrounds
INK         = "#1a1d21"   # --ink
INK_FAINT   = "#7a828c"   # --ink-faint
PAPER       = "#fbfaf8"   # --paper
WHITE       = "#ffffff"

# Wordmark typography mirrors the app's serif stack.
SERIF = "Georgia, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif"


# ---------------------------------------------------------------------------
# Shape primitives. Each returns a plain dict so the same data can drive
# either the SVG writer or the rasteriser.
# ---------------------------------------------------------------------------

def rect(x, y, w, h, fill):
    return {"t": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill}


def circle(cx, cy, r, fill):
    return {"t": "circle", "cx": cx, "cy": cy, "r": r, "fill": fill}


def ring(cx, cy, r, w, color, dash=None, offset=0.0):
    """A stroked circle. `dash` is (segment, gap) in path-length units."""
    return {"t": "ring", "cx": cx, "cy": cy, "r": r, "w": w,
            "stroke": color, "dash": dash, "offset": offset}


def line(x1, y1, x2, y2, w, color):
    """A stroked segment with round caps, which also gives round joins when
    segments are chained."""
    return {"t": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "w": w, "stroke": color}


# ---------------------------------------------------------------------------
# Concept 1 — Focus / Point
# ---------------------------------------------------------------------------

def c1_marks(ink=ACCENT, dot=PASS, bead=True):
    """Concentric focus. A solid point, one closed ring, and a broken outer
    ring that reads as an aperture opening outward.

    A single bead rides *on* the outer ring at the leading edge of the first
    arc, so it reads as a position advancing rather than as an ornament. On the
    ring rather than outside it keeps the mark exactly square, which matters
    for a favicon.
    """
    cx = cy = 32.0
    r_out = 21.0
    seg, gap = 37.0, 7.0
    shapes = [
        ring(cx, cy, 12.0, 3.2, ink),
        # Three arcs whose gaps are centred on 12, 4 and 8 o'clock, so the mark
        # keeps a vertical axis of symmetry.
        ring(cx, cy, r_out, 3.2, ink, dash=(seg, gap), offset=40.5),
    ]
    if bead:
        # Half a gap clockwise from 12 o'clock, on the ring path.
        theta = math.radians(0.5 * gap / (2 * math.pi * r_out) * 360.0)
        shapes.append(circle(cx + r_out * math.sin(theta),
                             cy - r_out * math.cos(theta), 2.9, dot))
    shapes.append(circle(cx, cy, 4.8, dot))
    return shapes


def c1_favicon(ink=ACCENT, dot=PASS):
    """16-32px: the broken ring and the bead are dropped. Two concentric
    elements with a wide gap between them survives 16px better than a busy
    aperture would.

    The ring is held at 9.5u and the centre filled solid, which keeps the
    centre visible even when the whole thing is scaled to 16px.
    """
    return [
        ring(16, 16, 9.5, 4.0, ink),
        circle(16, 16, 4.2, dot),
    ]


# ---------------------------------------------------------------------------
# Concept 2 — E + Focus
# ---------------------------------------------------------------------------

def c2_marks(ink=ACCENT, dot=PASS):
    """A geometric E. The two long arms and the short centre bar pull the eye
    to one point on the vertical axis — attention narrowing to a single spot.
    The mark stays a letter with no wordmark attached.

    The focus point is set clear of the arms' right edge so it reads as a
    separate mark rather than a lengthening of the centre bar.
    """
    return [
        rect(12, 8, 9, 48, ink),     # stem
        rect(21, 8, 28, 10, ink),    # upper arm, long
        rect(21, 46, 28, 10, ink),   # lower arm, long
        rect(21, 28, 15, 8, ink),    # centre bar, short: the focal plane
        circle(44.5, 32, 4.6, dot),  # one-pointed attention, on the axis
    ]


def c2_favicon(ink=ACCENT, dot=PASS):
    return [
        rect(6, 4, 5, 24, ink),
        rect(11, 4, 16, 5, ink),
        rect(11, 23, 16, 5, ink),
        rect(11, 14, 8, 4, ink),
        circle(23, 16, 2.4, dot),
    ]


# ---------------------------------------------------------------------------
# Concept 3 — Learning Path / Convergence
# ---------------------------------------------------------------------------

def c3_marks(ink=ACCENT, dot=PASS):
    """Three paths merge into one point and a single path continues onward.
    One node only, so it stays a mark rather than a network diagram.

    The approaches start on a shared left edge at three heights, which keeps
    the figure close to square: a wide mark reads as a diagram, not an icon.
    """
    px, py = 37.0, 32.0
    return [
        line(11, 10, px, py, 3.6, ink),
        line(11, 32, px, py, 3.6, ink),
        line(11, 54, px, py, 3.6, ink),
        line(px, py, 54, 32, 3.6, ink),
        circle(px, py, 4.8, dot),
    ]


def c3_favicon(ink=ACCENT, dot=PASS):
    px, py = 19.0, 16.0
    return [
        line(6, 7, px, py, 3.4, ink),
        line(6, 25, px, py, 3.4, ink),
        line(px, py, 27, 16, 3.4, ink),
        circle(px, py, 2.6, dot),
    ]


CONCEPTS = {
    "c1-focus-point": {
        "mark": c1_marks, "favicon": c1_favicon,
        "title": "Focus / Point",
    },
    "c2-e-focus": {
        "mark": c2_marks, "favicon": c2_favicon,
        "title": "E + Focus",
    },
    "c3-convergence": {
        "mark": c3_marks, "favicon": c3_favicon,
        "title": "Learning Path / Convergence",
    },
}


# ---------------------------------------------------------------------------
# SVG writer
# ---------------------------------------------------------------------------

def _n(v):
    """Trim trailing zeros so coordinates stay short."""
    if isinstance(v, int):
        return str(v)
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def shape_to_svg(s):
    t = s["t"]
    if t == "rect":
        return (f'<rect x="{_n(s["x"])}" y="{_n(s["y"])}" width="{_n(s["w"])}" '
                f'height="{_n(s["h"])}" fill="{s["fill"]}"/>')
    if t == "circle":
        return (f'<circle cx="{_n(s["cx"])}" cy="{_n(s["cy"])}" '
                f'r="{_n(s["r"])}" fill="{s["fill"]}"/>')
    if t == "ring":
        dash = ""
        if s["dash"]:
            seg, gap = s["dash"]
            dash = (f' stroke-dasharray="{_n(seg)} {_n(gap)}"'
                    f' stroke-dashoffset="{_n(s["offset"])}"')
        return (f'<circle cx="{_n(s["cx"])}" cy="{_n(s["cy"])}" r="{_n(s["r"])}" '
                f'fill="none" stroke="{s["stroke"]}" stroke-width="{_n(s["w"])}"{dash}/>')
    if t == "line":
        return (f'<path d="M{_n(s["x1"])} {_n(s["y1"])}L{_n(s["x2"])} {_n(s["y2"])}" '
                f'fill="none" stroke="{s["stroke"]}" stroke-width="{_n(s["w"])}" '
                f'stroke-linecap="round"/>')
    raise ValueError(t)


def mark_svg(shapes, size=64, title=None, bg=None):
    vb = 64
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}" '
           f'width="{size}" height="{size}" role="img">']
    if title:
        out.append(f'<title>{title}</title>')
    if bg:
        out.append(f'<rect width="{vb}" height="{vb}" fill="{bg}"/>')
    out.extend(shape_to_svg(s) for s in shapes)
    out.append("</svg>")
    return "\n".join(out) + "\n"


def favicon_svg(shapes, title=None):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" '
           'width="32" height="32" role="img">']
    if title:
        out.append(f"<title>{title}</title>")
    out.extend(shape_to_svg(s) for s in shapes)
    out.append("</svg>")
    return "\n".join(out) + "\n"


def lockup_svg(shapes, mark=54, title=None, ink=ACCENT, tag=INK_FAINT,
               word_ink=None, tag_ink=None):
    """Mark on the left, wordmark and tagline on the right.

    Text stays as <text> so the lockup remains editable and a few hundred
    bytes; convert to outlines before print production.
    """
    word_ink = word_ink or ink
    tag_ink = tag_ink or tag
    pad = 4
    gap = 18
    w = pad * 2 + mark + gap + 330
    h = mark + pad * 2
    scale = mark / 64.0
    tx = pad + mark + gap
    ty = pad + mark * 0.5

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(w)} {_n(h)}" '
           f'width="{_n(w)}" height="{_n(h)}" role="img">']
    if title:
        out.append(f"<title>{title}</title>")
    out.append(f'<g transform="translate({_n(pad)} {_n(pad)}) scale({_n(scale)})">')
    out.extend(shape_to_svg(s) for s in shapes)
    out.append("</g>")
    out.append(
        f'<text x="{_n(tx)}" y="{_n(ty - 3)}" font-family="{SERIF}" '
        f'font-size="25" letter-spacing="2.6" fill="{word_ink}">EKAGRA</text>')
    out.append(
        f'<text x="{_n(tx + 1)}" y="{_n(ty + 18)}" font-family="{SERIF}" '
        f'font-style="italic" font-size="13.5" letter-spacing="0.3" '
        f'fill="{tag_ink}">Adaptive Learning through AI</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Minimal rasteriser — enough to proof the geometry before it is trusted.
# Supersampled coverage over the four primitives above. No dependencies.
# ---------------------------------------------------------------------------

def _seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _in_shape(s, px, py):
    t = s["t"]
    if t == "rect":
        return (s["x"] <= px <= s["x"] + s["w"]) and (s["y"] <= py <= s["y"] + s["h"])
    if t == "circle":
        return math.hypot(px - s["cx"], py - s["cy"]) <= s["r"]
    if t == "ring":
        d = math.hypot(px - s["cx"], py - s["cy"])
        if abs(d - s["r"]) > s["w"] / 2:
            return False
        if s["dash"]:
            seg, gap = s["dash"]
            period = seg + gap
            # Arc length measured clockwise from 12 o'clock, matching the
            # rotate(-90) the SVG applies to the dash pattern.
            ang = math.degrees(math.atan2(px - s["cx"], -(py - s["cy"]))) % 360.0
            arc = ang / 360.0 * 2 * math.pi * s["r"]
            return ((arc - s["offset"]) % period) < seg
        return True
    if t == "line":
        return _seg_dist(px, py, s["x1"], s["y1"], s["x2"], s["y2"]) <= s["w"] / 2
    return False


def render_png(path, shapes, px=240, grid=64, bg=PAPER, ss=3, pad=0):
    """Render shapes to a PNG for visual proofing."""
    scale = (px - pad * 2) / grid
    ss = ss
    inv = 1.0 / scale
    bgv = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))

    rows = []
    for y in range(px):
        row = bytearray()
        for x in range(px):
            acc_r = acc_g = acc_b = 0
            for sy in range(ss):
                for sx in range(ss):
                    ux = (x + (sx + 0.5) / ss - pad) * inv
                    uy = (y + (sy + 0.5) / ss - pad) * inv
                    col = bgv
                    for s in shapes:
                        if _in_shape(s, ux, uy):
                            h = s.get("fill") or s.get("stroke")
                            col = tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
                    acc_r += col[0]
                    acc_g += col[1]
                    acc_b += col[2]
            n = ss * ss
            row += bytes((acc_r // n, acc_g // n, acc_b // n))
        rows.append(bytes(row))

    raw = b"".join(b"\x00" + r for r in rows)
    comp = zlib.compress(raw, 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", px, px, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", comp)
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)
    return path


# ---------------------------------------------------------------------------
# Emit everything
# ---------------------------------------------------------------------------

def write(path, content):
    full = os.path.join(HERE, path)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return full


def main():
    made = []
    proof = os.path.join(HERE, "_proofs")
    os.makedirs(proof, exist_ok=True)

    for key, info in CONCEPTS.items():
        name = info["title"]

        # colour mark
        made.append(write(f"{key}-mark.svg",
                          mark_svg(info["mark"](), 64, f"Ekagra — {name}")))

        # monochrome: one ink, the way a laser printer sees it
        made.append(write(f"{key}-mark-mono.svg",
                          mark_svg(info["mark"](ink=INK, dot=INK), 64,
                                   f"Ekagra — {name} (single colour)")))

        # reversed for dark slides
        made.append(write(f"{key}-mark-reversed.svg",
                          mark_svg(info["mark"](ink=WHITE, dot=PASS_LIGHT), 64,
                                   f"Ekagra — {name} (reversed)")))

        # header lockups
        made.append(write(f"{key}-lockup.svg",
                          lockup_svg(info["mark"](), title=f"Ekagra — {name}")))
        made.append(write(f"{key}-lockup-mono.svg",
                          lockup_svg(info["mark"](ink=INK, dot=INK),
                                     word_ink=INK, tag_ink=INK,
                                     title=f"Ekagra — {name} (single colour)")))

        # favicon
        made.append(write(f"{key}-favicon.svg",
                          favicon_svg(info["favicon"](), f"Ekagra — {name}")))

        # proofs for review
        render_png(os.path.join(proof, f"{key}-256.png"), info["mark"](), 256)
        render_png(os.path.join(proof, f"{key}-mono-256.png"),
                   info["mark"](ink=INK, dot=INK), 256)
        render_png(os.path.join(proof, f"{key}-favicon-32.png"),
                   info["favicon"](), 32, grid=32, ss=4, pad=0)
        render_png(os.path.join(proof, f"{key}-favicon-16.png"),
                   info["favicon"](), 16, grid=32, ss=6, pad=0)

    for f in sorted(made):
        print(f"{os.path.basename(f):34s} {os.path.getsize(f):6d} bytes")


if __name__ == "__main__":
    main()
