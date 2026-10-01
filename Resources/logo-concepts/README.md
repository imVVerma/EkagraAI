# Ekagra — logo concepts

Three candidate marks for **Ekagra / Adaptive Learning through AI**, drawn as
lightweight SVGs. Nothing here is wired into the application.

Open `preview.html` from this folder to compare them side by side.

## The three concepts

| | Concept | Idea |
|---|---|---|
| 1 | **Focus / Point** | A point, one closed ring, and an aperture opening outward with a bead riding its edge. One-pointed attention; learning expanding from a focused idea. |
| 2 | **E + Focus** | A geometric E whose two long arms and short centre bar narrow attention to one point on its axis. |
| 3 | **Learning Path / Convergence** | Three paths merge into one point, and a single path continues onward. |

## Files

For each concept `cN-…`:

| Suffix | Purpose |
|---|---|
| `-mark.svg` | 64×64, two-colour. Header, slides, and anywhere the mark stands alone. |
| `-mark-mono.svg` | 64×64, single ink. Monochrome printing, fax, photocopies. |
| `-mark-reversed.svg` | 64×64, light on transparent. Dark slide backgrounds. |
| `-lockup.svg` | Mark + wordmark + tagline. Website header. |
| `-lockup-mono.svg` | The same lockup in one ink. |
| `-favicon.svg` | 32×32, simplified. Browser tab. |

The largest file is about 1 KB. Everything is drawn with `rect`, `circle` and
straight `path` segments — no icon library, no fonts, no raster images, no
external references.

## Design constraints held

- No robots, brains, neural networks, circuits, chat bubbles, or lightbulbs.
- Colours are taken from `frontend/styles.css`: teal `#1f4e5f` (the `--accent`
  already in use) and green `#2f6b4f` (`--pass`). Monochrome versions collapse
  to `#1a1d21` (`--ink`).
- The wordmark uses the application's serif stack.
- Favicons are genuinely reduced, not just scaled: concept 1 drops the bead and
  the broken ring, concept 3 drops one approach path.

## Verification

`check_geometry.py` encodes the properties the design depends on and checks
them numerically — because these marks cannot be eyeballed reliably at 16px.
It asserts, per concept:

- the mark sits inside its viewBox with a margin
- the thinnest stroke survives 24px (the full mark's floor; the favicon covers 16px)
- parts that should read as separate do not touch at small sizes
- the single-ink version really is one colour
- the palette stays inside the app's existing colours
- the favicon is no more complex than the mark, fills its box, keeps an edge
  margin, and holds ≥1px strokes at 16px
- concept 1's dash pattern closes after exactly three arcs with the gaps
  symmetrically placed, and the bead sits on the ring
- concept 2 is genuinely an E, with a short centre bar and the focus point
  clear of it
- concept 3 has exactly one node, one onward path, three distinct approach
  angles, and symmetry about the horizontal axis

Run it with:

```
python3 build_logos.py      # regenerate every asset
python3 check_geometry.py   # verify the geometry
```

Both use only the standard library. `build_logos.py` also writes PNG proofs to
`_proofs/` (a scratch folder, not part of the deliverable) so the geometry can
be rasterised without a browser.

## Not decided

No concept has been chosen and nothing has been added to the app. The lockups
keep the wordmark as `<text>`, so the serif falls back to whatever the viewer
has; convert the text to outlines before print production.
