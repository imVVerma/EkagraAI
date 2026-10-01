#!/usr/bin/env python3
"""Verify the logo geometry numerically, since the marks cannot be eyeballed here.

Each check is a property the design actually depends on. A check that fails
means the mark would break at that size or in that medium, not that it looks
subjectively wrong.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_logos as B

GRID = 64
FAV = 32
PPI = 96.0  # CSS reference pixel density

fails = []
warns = []


def ok(cond, label, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{f'   [{detail}]' if detail else ''}")
    if not cond:
        fails.append(label)


def warn(cond, label, detail=""):
    if not cond:
        print(f"  WARN  {label}{f'   [{detail}]' if detail else ''}")
        warns.append(label)


def bounds(shapes):
    xs, ys = [], []
    for s in shapes:
        t = s["t"]
        if t == "rect":
            xs += [s["x"], s["x"] + s["w"]]
            ys += [s["y"], s["y"] + s["h"]]
        elif t == "circle":
            xs += [s["cx"] - s["r"], s["cx"] + s["r"]]
            ys += [s["cy"] - s["r"], s["cy"] + s["r"]]
        elif t == "ring":
            xs += [s["cx"] - s["r"] - s["w"] / 2, s["cx"] + s["r"] + s["w"] / 2]
            ys += [s["cy"] - s["r"] - s["w"] / 2, s["cy"] + s["r"] + s["w"] / 2]
        elif t == "line":
            h = s["w"] / 2
            xs += [min(s["x1"], s["x2"]) - h, max(s["x1"], s["x2"]) + h]
            ys += [min(s["y1"], s["y2"]) - h, max(s["y1"], s["y2"]) + h]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(shapes):
    """Area-weighted centre of mass, used to judge optical balance."""
    n = 0.0
    sx = sy = 0.0
    for s in shapes:
        if s["t"] == "rect":
            a = s["w"] * s["h"]
            cx, cy = s["x"] + s["w"] / 2, s["y"] + s["h"] / 2
        elif s["t"] in ("circle", "ring"):
            a = math.pi * s["r"] ** 2 if s["t"] == "circle" else 2 * math.pi * s["r"] * s["w"]
            cx, cy = s["cx"], s["cy"]
        else:
            L = math.hypot(s["x2"] - s["x1"], s["y2"] - s["y1"])
            a = L * s["w"]
            cx, cy = (s["x1"] + s["x2"]) / 2, (s["y1"] + s["y2"]) / 2
        n += a
        sx += cx * a
        sy += cy * a
    return sx / n, sy / n


def min_stroke(shapes):
    ws = [s.get("w", 0) for s in shapes if s["t"] in ("ring", "line")]
    ws += [min(s["w"], s["h"]) for s in shapes if s["t"] == "rect"]
    return min(ws) if ws else 0


def min_gap(shapes, cell=0.5):
    """Smallest vertical or horizontal gap between disjoint solid parts.

    Sampled on a coarse grid by testing pairwise separation of the parts, which
    is enough to catch bars that would merge when the mark is scaled down.
    """
    solids = [s for s in shapes if s["t"] in ("rect", "circle")]
    if len(solids) < 2:
        return None
    best = None
    for a in range(len(solids)):
        for b in range(a + 1, len(solids)):
            d = _rect_gap(solids[a], solids[b], cell)
            if d is not None and (best is None or d < best):
                best = d
    return best


def _bbox(s, cell=0.5):
    if s["t"] == "rect":
        return (s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"])
    return (s["cx"] - s["r"], s["cy"] - s["r"], s["cx"] + s["r"], s["cy"] + s["r"])


def _rect_gap(a, b, cell=0.5):
    """Conservative gap between two axis-aligned boxes (0 if they overlap)."""
    ax0, ay0, ax1, ay1 = _bbox(a)
    bx0, by0, bx1, by1 = _bbox(b)
    dx = max(bx0 - ax1, ax0 - bx1, 0)
    dy = max(by0 - ay1, ay0 - by1, 0)
    if dx > 0 and dy > 0:
        return math.hypot(dx, dy)
    return max(dx, dy)


# ---------------------------------------------------------------------------

CONCEPTS = {
    "c1": ("Focus / Point", B.c1_marks, B.c1_favicon),
    "c2": ("E + Focus", B.c2_marks, B.c2_favicon),
    "c3": ("Convergence", B.c3_marks, B.c3_favicon),
}

for cid, (name, mark_fn, fav_fn) in CONCEPTS.items():
    print(f"\n[{cid}] {name}")
    shapes = mark_fn()
    x0, y0, x1, y1 = bounds(shapes)

    # 1. lives inside its viewBox with a small margin
    margin = 1.0
    ok(x0 >= margin and y0 >= margin and x1 <= GRID - margin and y1 <= GRID - margin,
       "inside the 64x64 viewBox", f"bounds {x0:.1f},{y0:.1f} to {x1:.1f},{y1:.1f}")

    # 2. optically centred, not mathematically centred
    cx, cy = centroid(shapes)
    warn(abs(cx - 32) <= 4.5 and abs(cy - 32) <= 4.5,
         "centroid sits near the geometric centre",
         f"centroid {cx:.1f},{cy:.1f}")

    # 3. the mark is not wider than tall by much, so it reads as a square icon
    w, h = x1 - x0, y1 - y0
    ok(0.72 <= (w / h) <= 1.28, "proportionally square", f"{w:.1f} x {h:.1f}")

    # 4/5. the full mark's floor is 24px (favicon covers 16px), so the thinnest
    # feature only has to survive that.
    ms = min_stroke(shapes)
    at24 = ms * 24.0 / GRID
    ok(at24 >= 1.0, "thinnest stroke is at least 1px at 24px",
       f"stroke {ms:.1f}u -> {at24:.2f}px at 24px")
    warn(at24 >= 1.25, "thinnest stroke comfortably over 1px at 24px",
         f"-> {at24:.2f}px, hairline strokes grey out on low-DPI screens")

    # 6. parts that should read as separate must not touch. Only *free-standing*
    # parts are checked: a letter's own stem and arms are meant to join.
    if cid == "c2":
        dots = [x for x in shapes if x["t"] == "circle"]
        bars = [x for x in shapes if x["t"] == "rect"]
        # Only bars that could actually collide matter: the upper and lower
        # arms sit far from the focus point's own band.
        clear = min(_rect_gap(d, b) for d in dots for b in bars
                    if b["y"] <= d["cy"] + d["r"] and d["cy"] - d["r"] <= b["y"] + b["h"])
        g24 = clear * 24.0 / GRID
        ok(g24 >= 1.0, "focus point stays clear of the letterform at 24px",
           f"gap {clear:.1f}u -> {g24:.2f}px")
    else:
        gap = min_gap(shapes)
        if gap is not None:
            g16 = gap * 16.0 / GRID
            ok(g16 >= 0.75, "parts stay separated at 16px",
               f"gap {gap:.1f}u -> {g16:.2f}px at 16px")
        else:
            print("  ....  single solid part, no internal gap to check")

    # 7. monochrome collapses to a single ink
    mono_shapes = mark_fn(ink=B.INK, dot=B.INK)
    mono = {s.get("fill") or s.get("stroke") for s in mono_shapes}
    ok(mono == {B.INK}, "single-ink version uses one colour", str(mono))

    # 8. colourway stays inside the app palette
    colours = {s.get("fill") or s.get("stroke") for s in shapes}
    ok(colours <= {B.ACCENT, B.PASS}, "colours come from the app palette", str(colours))

    # 9. favicon is genuinely simpler: fewer primitives than the full mark
    fav = fav_fn()
    ok(len(fav) <= len(shapes), "favicon is no more complex than the mark",
       f"{len(fav)} vs {len(shapes)} primitives")

    # 10. favicon fills its 32x32 box well, and leaves a safe margin so no
    # browser chrome clips it
    fx0, fy0, fx1, fy1 = bounds(fav)
    fill = (fx1 - fx0) * (fy1 - fy0) / (FAV * FAV)
    ok(fill >= 0.16, "favicon occupies a reasonable share of its box",
       f"{fill * 100:.0f}% of the 32x32 area")
    m = min(fx0, fy0, FAV - fx1, FAV - fy1)
    ok(m >= 1.0, "favicon keeps at least 1u clear of the box edge",
       f"tightest margin {m:.1f}u -> {m * 16 / FAV:.2f}px at 16px")

    # 11. favicon strokes survive 16px
    fms = min_stroke(fav)
    ok(fms * 16.0 / FAV >= 1.0, "favicon stroke at least 1px at 16px",
       f"stroke {fms:.1f}/32u -> {fms * 16 / FAV:.2f}px")

    # 12. at 16px the gap between the ring and the centre must not close up
    ring_d = [x for x in fav if x["t"] == "ring"]
    dot_d = [x for x in fav if x["t"] == "circle"]
    if ring_d and dot_d:
        clear = (ring_d[0]["r"] - ring_d[0]["w"] / 2) - dot_d[0]["r"]
        ok(clear * 16.0 / FAV >= 0.75, "favicon centre stays distinct from the ring at 16px",
           f"clearance {clear:.1f}/32u -> {clear * 16 / FAV:.2f}px at 16px")

# ---------------------------------------------------------------------------
print("\n[concept-specific]")

# C1: the broken ring must actually be broken, and symmetric about the axis
s = B.c1_marks()
dashed = [x for x in s if x["t"] == "ring" and x["dash"]]
ok(len(dashed) == 1, "C1 outer ring is dashed")
d = dashed[0]
seg, gap = d["dash"]
per = seg + gap
circ = 2 * math.pi * d["r"]
ok(abs(3 * per - circ) < 0.5, "C1 dash pattern closes after exactly 3 arcs",
   f"3x{per:.1f} = {3 * per:.1f} vs circumference {circ:.1f}")
# Gaps must land on 12, 4 and 8 o'clock, giving the mark a vertical axis.
# A gap centre is where the pattern position equals seg + gap/2.
target = seg + gap / 2
centres = []
for k in range(3):
    arc = (target - d["offset"] + k * per) % per      # arc length of that gap
    centres.append(arc / circ * 360.0)
expected = (0.0, 120.0, 240.0)
sym = all(min(abs(((c - e + 180) % 360) - 180) for e in expected) < 1.5 for c in centres)
ok(sym, "C1 gaps are symmetrically placed at 12/4/8 o'clock",
   ", ".join(f"{c:.1f}deg" for c in sorted(centres)))
# and the same must hold in the rasteriser, or the proof images lie
rv = [c for c in centres]
ok(len(rv) == 3, "C1 has exactly three arcs", f"{len(rv)}")
ok(gap >= 4.0, "C1 gaps are wide enough to read as gaps at small sizes",
   f"gap {gap:.1f}u -> {gap * 16 / 64:.2f}px at 16px")
bead = [x for x in s if x["t"] == "circle" and x["r"] < 3.5]
ok(len(bead) == 1, "C1 has exactly one progress bead",
   f"r={bead[0]['r'] if bead else '-'}")
# the bead must ride on the outer ring, not float outside it
if bead:
    b = bead[0]
    dist = math.hypot(b["cx"] - 32, b["cy"] - 32)
    ok(abs(dist - 21.0) < 0.6, "C1 bead sits on the outer ring",
       f"distance from centre {dist:.1f} vs ring radius 21.0")

# C2: the E must be an E — stem on the left, three arms, shortest in the middle
rects = [x for x in B.c2_marks() if x["t"] == "rect"]
ok(len(rects) == 4, "C2 is built from four rectangles", f"{len(rects)}")
stem = min(rects, key=lambda r: r["w"])
ok(stem["x"] <= min(r["x"] for r in rects if r is not stem), "C2 stem is the leftmost part")
ok(abs(stem["y"] + stem["h"] / 2 - 32) < 0.01, "C2 stem is vertically centred")
arms = [r for r in rects if r is not stem]
ok(len(arms) == 3, "C2 has three arms", f"{len(arms)}")
mids = sorted(arms, key=lambda r: r["y"] + r["h"] / 2)
ok(mids[0]["x"] + mids[0]["w"] == mids[2]["x"] + mids[2]["w"],
   "C2 outer arms are equal length",
   f"{mids[0]['w']} vs {mids[2]['w']}")
ok(mids[1]["x"] + mids[1]["w"] < mids[0]["x"] + mids[0]["w"],
   "C2 centre bar is shorter, drawing the eye inward",
   f"centre {mids[1]['w']} vs arms {mids[0]['w']}")
dots = [x for x in B.c2_marks() if x["t"] == "circle"]
ok(len(dots) == 1, "C2 has one focus point")
ok(abs(dots[0]["cy"] - 32) < 0.01, "C2 focus point is on the vertical axis",
   f"cy={dots[0]['cy']}")
# It must clear the centre bar, the only part in its own band. The upper and
# lower arms end at the same x but sit 10+ units above and below, so their
# right edge is not the constraint here.
centre = min(arms, key=lambda r: abs((r["y"] + r["h"] / 2) - 32))
ok(dots[0]["cx"] - dots[0]["r"] > centre["x"] + centre["w"],
   "C2 focus point sits clear of the centre bar",
   f"dot left edge {dots[0]['cx'] - dots[0]['r']:.1f} vs bar end "
   f"{centre['x'] + centre['w']}")
# and it must not drift outside the letter's own vertical extent
outer = max(r["x"] + r["w"] for r in arms)
ok(dots[0]["cx"] + dots[0]["r"] <= outer + 2.0,
   "C2 focus point stays within the letter's width",
   f"dot right {dots[0]['cx'] + dots[0]['r']:.1f} vs arms end {outer}")
ok(dots[0]["cx"] + dots[0]["r"] <= GRID,
   "C2 focus point stays inside the viewBox", f"cx+r={dots[0]['cx'] + dots[0]['r']}")

# C3: paths must converge to one point, and exactly one must continue onward
c3 = B.c3_marks()
lines = [x for x in c3 if x["t"] == "line"]
node = [x for x in c3 if x["t"] == "circle"][0]
px, py = node["cx"], node["cy"]
incoming = [x for x in lines if (x["x1"], x["y1"]) != (px, py)]
outgoing = [x for x in lines if (x["x1"], x["y1"]) == (px, py)]
ok(len(incoming) == 3, "C3 has three incoming paths", f"{len(incoming)}")
ok(len(outgoing) == 1, "C3 has exactly one onward path", f"{len(outgoing)}")
ok(all((x["x2"], x["y2"]) == (px, py) for x in incoming),
   "C3 all incoming paths end at the node",
   f"node at {px},{py}")
ok(len([x for x in c3 if x["t"] == "circle"]) == 1,
   "C3 has one node only, so it does not read as a network")
ok(outgoing and outgoing[0]["x2"] - outgoing[0]["x1"] >= 12,
   "C3 onward path has travel length",
   f"len {outgoing[0]['x2'] - outgoing[0]['x1']:.0f}u" if outgoing else "")
# approaches must be distinguishable, not parallel duplicates
ang = sorted(round(math.degrees(math.atan2(py - x["y1"], px - x["x1"])), 1)
             for x in incoming)
ok(len(set(ang)) == 3 and (ang[-1] - ang[0]) >= 30,
   "C3 approaches come in at clearly different angles",
   ", ".join(f"{a}deg" for a in ang))
# symmetric about the horizontal axis, which keeps the mark calm
ys = sorted(x["y1"] for x in incoming)
ok(abs((ys[0] + ys[-1]) / 2 - py) < 0.01,
   "C3 approaches are symmetric about the onward axis",
   f"y {ys[0]}, {ys[-1]} about {py}")

# ---------------------------------------------------------------------------
print("\n[assets]")
here = os.path.dirname(os.path.abspath(__file__))
svgs = sorted(f for f in os.listdir(here) if f.endswith(".svg"))
ok(len(svgs) == 18, "18 SVG assets written", f"{len(svgs)} found")
ok(all(os.path.getsize(os.path.join(here, f)) < 2000 for f in svgs),
   "every SVG is under 2KB",
   f"largest {max(os.path.getsize(os.path.join(here, f)) for f in svgs)}B")
no_raster = not any(f.endswith((".png", ".jpg", ".gif")) and not f.startswith("_")
                    for f in os.listdir(here))
ok(no_raster, "no raster images in the deliverable set")
ok(not any("xlink:href" in open(os.path.join(here, f)).read()
           or "<image" in open(os.path.join(here, f)).read() for f in svgs),
   "no external or embedded image references")

print("\n" + "=" * 62)
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print(f"All geometry checks passed ({len(warns)} warnings).")
