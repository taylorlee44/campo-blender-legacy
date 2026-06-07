# campo-blender-legacy

**Archived Blender/MPFB rendering path from the CampoBlender project.**

This code is no longer in active development. The active project lives at
[CampoBlender](https://github.com/taylorlee44/CampoBlender) and uses SMPL +
PyVista + a Next.js web tool instead of headless Blender.

---

## What's here

### `campo/blender/`

The original headless Blender rendering pipeline. Takes a scene JSON, loads a
pre-built character `.blend`, applies MPFB-based pose and clothing, places a
camera at the requested shot/angle, and renders a Workbench PNG.

```
entry.py      ← CLI entry point — what `blender -P` runs
scene.py      ← Top-level scene builder
character.py  ← Character loading / MPFB spawning / rigging / posing
clothing.py   ← OBJ clothing import + scale correction
camera.py     ← Camera placement and shot framing math
render.py     ← Workbench render configuration
```

### `assets/`

- `person.blend` — Pre-built Claudia character with MPFB rig (6.6 MB)
- `clothing/` — Bundled CC0 OBJ clothing assets for the character

### `scripts/`

- `export_shots.py` — Blender headless: export 3 preset reference shots
- `render_batch.py` — Blender headless: grid render all angles × shot sizes

### `docs/blender.md`

Setup guide for headless Blender + MPFB on macOS.

### `recon-spike/`

Research spike for server-side room reconstruction via gaussian splatting.
ARKit pose capture schema, gsplat reconstruction script, and a Spark viewer.

---

## Why it was retired

- Headless Blender on Apple Silicon (MPS) had driver/MPS conflicts and non-deterministic renders
- MPFB 2.0.15 macro API required workarounds that broke across minor Blender updates
- SMPL + PyVista produces equivalent geometry in milliseconds without Blender installed
- The web tool's live R3F viewport makes a pre-rendered PNG reference frame redundant

---

## Requirements (if you want to run it)

| Component | Version |
|-----------|---------|
| Blender | 5.1.x |
| MPFB | 2.0.15+ |
| Python | 3.13 (bundled with Blender) |

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  -b assets/person.blend \
  -P campo/blender/entry.py
```
