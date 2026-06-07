# Blender Reference

Hard-won patterns from the Blender 5.1.x headless rendering path (`campo/blender/`).
This path is not currently active — the SMPL/PyVista path is used for all development.
Keep this doc if the Blender path is revived or extended.

---

## Running Locally

**Scripting tab (GUI):** open `pipeline/storyboard_scene.py` in the Text Editor, click Run Script or `Alt+P`.

**Headless:**
```bash
/Applications/Blender.app/Contents/MacOS/Blender -b assets/person.blend -P pipeline/storyboard_scene.py
```
The character `.blend` file must be passed as the base file (`-b assets/person.blend`) so that the character mesh is already in the scene when the script runs.

**Entry point convention:** Blender scripts call their entry function unconditionally at module level — `if __name__ == "__main__":` guards don't apply:
```python
build_scene()  # runs in both GUI (Run Script) and headless (-P) modes
```

---

## Blender API Rules

**Always use data-block access over operators:**
```python
# ✓ headless-safe
bpy.data.objects.remove(obj, do_unlink=True)

# ✗ requires window-manager context
bpy.ops.object.delete()
```

**Use `bpy.context.temp_override` for complex addon ops (like MPFB) that inspect `context.active_object` internally. Pass only the keys you need — never spread a full `bpy.context.copy()` dict:**
```python
seed_mesh = bpy.data.meshes.new("_seed")
temp_obj = bpy.data.objects.new("_seed", seed_mesh)
bpy.context.scene.collection.objects.link(temp_obj)
bpy.context.view_layer.objects.active = temp_obj

with bpy.context.temp_override(object=temp_obj, active_object=temp_obj):
    HumanService.create_human()

bpy.data.objects.remove(temp_obj, do_unlink=True)
```

**Units are always meters.** 1 Blender unit = 1 metre.

**Never hardcode spatial constants** — always derive from bounding box:
```python
corners = [actor.matrix_world @ Vector(c) for c in actor.bound_box]
```

**Camera rotation:** use `direction.to_track_quat('-Z', 'Y').to_euler()`. Never hardcode `rotation_euler`.

**Geometry creation** — prefer `bmesh` over `bpy.ops.mesh.primitive_*_add`:
```python
# ✓
mesh = bpy.data.meshes.new("Floor_Mesh")
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3.0)
bm.to_mesh(mesh)
bm.free()
floor = bpy.data.objects.new("Floor", mesh)
bpy.context.scene.collection.objects.link(floor)
```

**Logging** — always pass `stream=sys.__stdout__` to `basicConfig`. Blender headless replaces `sys.stdout`/`sys.stderr` with custom wrappers that create an infinite output-capture feedback loop:
```python
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.__stdout__)
```

---

## MPFB 2 Notes

- Extensions registered as `bl_ext.blender_org.mpfb` or `bl_ext.user_default.mpfb` — not bare `mpfb`. Detect by iterating `addon_utils.modules()` and matching `.endswith("mpfb")`.

- **Never use `from mpfb.services.X import Y`** — cache the module reference:
  ```python
  _MPFB_MOD = sys.modules.get(module_name)
  TargetService = _MPFB_MOD.services.targetservice.TargetService
  ```

- **`create_human()` accepts `macro_detail_dict`** (MPFB 2.0.15+). Seed from `TargetService.get_default_macro_info_dict()` and `.update()` with overrides. Required keys: `cupsize`, `firmness`, `race` (nested dict). Do NOT call `calculate_target_stack_from_macro_info_dict` + `bulk_load_targets` directly — format mismatch.

- **`bpy.ops.mpfb.add_standard_rig` must NOT run inside `temp_override`** — it reads `bpy.context.object` internally to find the armature. Set `view_layer.objects.active` directly:
  ```python
  bpy.context.view_layer.objects.active = actor
  actor.select_set(True)
  bpy.context.view_layer.update()
  bpy.ops.mpfb.add_standard_rig()   # no temp_override
  ```

- **Finding the rig after `add_standard_rig`**: check in order — armature as parent, armature as child, Armature modifier, any armature in scene.

- Find the human via `bpy.data.objects["makehuman_human"]` with a mesh-list fallback.

---

## Clothing Assets

Bundled CC0 clothing (shirt + pants) in `assets/clothing/`.

**Loading strategy:**
1. **MPFB `ClothesService.fit_clothes_to_human`** (primary) — import OBJ, then call `fit_clothes_to_human(actor, clothing_obj, mhclo_path)`.
2. **Direct OBJ import** (fallback) — OBJs are in MakeHuman internal units (7.5 MH units ≈ 1.495m). Apply `scale = actor_height / 7.5`; pants need additional Z-translate of `abs(pants_z_min * scale)`.

**Never** use `ClothesService.load_clothes_from_mhclo` or `load_mhclo_and_create_clothes_object` — these don't exist in MPFB 2.0.15.

**Actor bounding box reference** (default macro young-adult male, MPFB 2.0.15):
- Height: 1.4951m, feet Z=0, head Z=1.4951
- Width (X): ±0.4736m, Depth (Y): −0.311 to +0.085m

---

## Render

- Engine: `BLENDER_WORKBENCH` — fast, headless-safe, clean geometry reference for ControlNet.
- Resolution: 1920×1080.
- Output: PNG to path from config or CLI.

---

## Known Blender 5.x Gotchas

| Error | Cause | Fix |
|---|---|---|
| `AttributeError: 'Context' has no attribute 'active_object'` | No window manager headless | Use `bpy.data` directly |
| `TypeError: create_human() got unexpected keyword argument 'name'` | MPFB 2 removed `name` param | Call with no args, rename after |
| `AttributeError: 'Mesh' object has no attribute 'display_type'` | `temp_override` locked context during `add_standard_rig` | Call without `temp_override` |
| `No module named 'mpfb'` | MPFB is a `bl_ext.*` extension | Use `sys.modules.get()` cache |
| Infinite `INFO: INFO: INFO:` loop | `logging.basicConfig` targeting `sys.stdout` | Use `stream=sys.__stdout__` |
| `RecursionError` in `objects.remove()` | 3D-Agent addon fires on deletion | Don't call `clear_scene()` with blend base file |
| Character renders black | `hide_render=True` on collection in source `.blend` | Set `col.hide_render = False` after load |
