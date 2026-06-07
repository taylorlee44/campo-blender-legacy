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
See the **Recon spike** section below for the state this left off at.

---

## Why it was retired

- Headless Blender on Apple Silicon had MPS/driver conflicts and non-deterministic renders
- MPFB 2.0.15 macro API required workarounds that broke across minor Blender updates
- SMPL + PyVista produces equivalent geometry in milliseconds without Blender installed
- The web tool's live R3F viewport makes a pre-rendered PNG reference frame redundant

---

## If you pick this up again

### Requirements

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

---

### Known Blender 5.x headless gotchas

These cost significant debugging time. All fixes are already applied in the code.

**1. Logging feedback loop**

Always use `stream=sys.__stdout__` in `logging.basicConfig`. Blender headless
replaces `sys.stdout` with a custom wrapper that re-echoes output back through its
own logging capture, creating an infinite `INFO: INFO: INFO:...` loop that crashes
with `RecursionError`. `sys.__stdout__` is Python's original pre-Blender stdout.

```python
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.__stdout__)
```

**2. Don't call `clear_scene()` with a character `.blend` base**

The 3D-Agent (BlenderGPT) addon registers a driver-namespace hook that fires on
every `bpy.data.objects.remove()` call, re-entering the scene update and causing
Python recursion. Load the character `.blend` directly with `blender -b` and never
call `clear_scene()` — the character is already there.

**3. `active_object` missing from context in headless**

There is no window manager in headless mode. Never rely on `bpy.context.active_object`
after calling an operator. Use `bpy.data` to look objects up by name directly.

**4. `add_standard_rig` must NOT use `temp_override`**

`bpy.ops.mpfb.add_standard_rig` internally reads `bpy.context.object` to get the
new armature. A `temp_override(object=mesh)` locks that value for the entire operator,
so MPFB assigns the mesh as the armature and crashes at `mesh.data.display_type = 'WIRE'`.

Fix (already in `character.py`):
```python
bpy.context.view_layer.objects.active = actor
actor.select_set(True)
bpy.context.view_layer.update()
bpy.ops.mpfb.add_standard_rig()
```

---

### MPFB 2.0.15 module access

Never bare-import MPFB. It's registered as `bl_ext.blender_org.mpfb` (or
`bl_ext.user_default.mpfb`), not the bare name `mpfb`. The code caches it:

```python
_MPFB_MOD = sys.modules.get("bl_ext.blender_org.mpfb")  # or user_default
```

`create_human()` accepts `macro_detail_dict` directly — do NOT call
`calculate_target_stack_from_macro_info_dict` + `bulk_load_targets` separately
(format mismatch between those two). Always seed from
`TargetService.get_default_macro_info_dict()` and `.update()` with overrides.

Armature lookup: MPFB 2 may place the rig as parent, child, modifier target, or
collection sibling — `_find_armature` checks all four.

---

### Arm posing — what was solved and what wasn't

**Rain (CloudRig) — SOLVED** (`_pose_rain_ik_arms()` in `character.py`)

Rain uses CloudRig, not standard Rigify. The working approach: move `IK-Hand.L`
and `IK-Hand.R` — these are free bones with no constraints and are the real IK
levers. Moving them straight below the shoulder moves the full deformation chain.

What doesn't work: rotating FK bones directly, muting COPY_TRANSFORMS, or moving
IK-Arm_Stretch.L head (it's co-located with the shoulder so delta=0).

Key math:
```python
shld = bones["IK-Upperarm.L"].bone.head_local
hand = bones["IK-Hand.L"]
arm_len = (hand.bone.head_local - shld).length       # ~0.416 m
target_arm = Vector((shld.x, shld.y, shld.z - arm_len))
delta = target_arm - hand.bone.head_local
hand.location = hand.bone.matrix_local.to_3x3().inverted() @ delta
bpy.context.view_layer.update()
```

Also move `IK-Pole-Forearm.L/R` down by the same Z delta as `IK-Hand`, or the
elbow bends outward.

**Claudia (UE4 rig, `person.blend`) — UNSOLVED**

Armature scale=0.01, rotation=90° X (armature Y = world Z). After clearing the
baked animation action (`arm_obj.animation_data.action = None`), rotating
`upperarm_l/r` by X=-90° only drops the arm ~14 cm (expected ~35 cm for full
arm-at-side). Root cause unknown — likely a twist/corrective bone chain sitting
on top of upperarm that isn't being driven.

**Simplest production workaround for Claudia:** manually pose the arms in Blender
GUI and save as the default pose in `person.blend`. The headless pipeline renders
it as-is. Production character pipelines are designed to be animated through their
control bone hierarchy — fighting them programmatically is rarely worth it.

---

### Recon spike — where it left off

`recon-spike/` is a research spike for server-side gaussian-splat room reconstruction
from iPhone capture. It was at **M0 — quality proof**, not yet completed.

**What was done:**
- iOS capture bundle received: 95 frames, 1920×1440, iPhone SE 3rd gen (non-LiDAR)
  at `/Users/taylorlee/Developer/CampoScanning/from_taylor/2026-06-02T05-34-51Z`
- Bundle validated by `recon-spike/capture_schema.py` — all checks pass
- 6 Colab notebook cells written and ready to paste (see below)
- `bundle.zip` was uploaded to a Colab session — **NOT YET RUN** (session may have expired)

**What's next:** Open Google Colab (free T4 GPU), paste these 6 cells top-to-bottom,
run in order, download `.ply`, load in `recon-spike/viewer/index.html`.

```python
# Cell 1 — unzip
import zipfile, os
with zipfile.ZipFile("/content/bundle.zip", "r") as z:
    z.extractall("/content/bundle")
print("files:", len(os.listdir("/content/bundle/frames")))

# Cell 2 — install nerfstudio (~5 min)
!pip install nerfstudio -q

# Cell 3 — convert capture.json → transforms.json (ARKit poses pass through directly)
import json, shutil
from pathlib import Path
bundle = Path("/content/bundle")
with open(bundle / "capture.json") as f:
    cap = json.load(f)
transforms = {
    "camera_model": "OPENCV",
    "fl_x": cap["intrinsics"]["fx"],
    "fl_y": cap["intrinsics"]["fy"],
    "cx": cap["intrinsics"]["cx"],
    "cy": cap["intrinsics"]["cy"],
    "w": cap["intrinsics"]["width"],
    "h": cap["intrinsics"]["height"],
    "frames": [
        {
            "file_path": f"frames/{fr['filename']}",
            "transform_matrix": fr["transform_matrix"],
        }
        for fr in cap["frames"] if fr.get("blur_score", 1) > 2.0
    ]
}
with open(bundle / "transforms.json", "w") as f:
    json.dump(transforms, f)
print(f"kept {len(transforms['frames'])} frames")

# Cell 4 — train (~10–20 min on T4)
!ns-train splatfacto \
    --data /content/bundle \
    --output-dir /content/output \
    --viewer.quit-on-train-completion True \
    nerfstudio-data --eval-mode fraction

# Cell 5 — export .ply
!ns-export gaussian-splat \
    --load-config /content/output/splatfacto/*/config.yml \
    --output-dir /content/splat

# Cell 6 — download
from google.colab import files
import glob
ply = glob.glob("/content/splat/*.ply")[0]
files.download(ply)
```

**After download:** load the `.ply` in `recon-spike/viewer/index.html` (the Spark
viewer — drag `.ply` onto the page). Compare with a Scaniverse scan of the same
room if available.

**Go/no-go decision:** if the quality is Polycam-grade, proceed to M1 (contract lock
+ iOS app + pipeline build). If not, either improve capture quality or reconsider
the reconstruction approach.

**Note on blur gating:** frames 1–4 in the test bundle have blur=0 and pos_delta=0
(camera warmup artifact). The blur gate was disabled during capture — p10 blur=5.4
is a reasonable threshold to re-enable for next capture.
