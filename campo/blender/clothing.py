"""
Clothing loader for the Campo storyboard pipeline.

Loads bundled CC0 shirt and pants assets via OBJ import and scales them to
fit the actor. MPFB's fit_clothes_to_human is attempted first; the OBJ
scale-correction fallback is used when ClothesService is unavailable.

Asset notes:
  - OBJs are in MakeHuman internal units (full body ≈ 7.5 MH units ≈ 1.495m actor).
  - Scale factor = actor_height / 7.5.
  - Pants OBJ origin is at the waist; leg geometry runs downward to Z ≈ -7.52.
    After scaling, vertices above crotch level (52% of body height) are clipped.
"""

import logging
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

logger = logging.getLogger(__name__)

_CLOTHING_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "clothing"

_CLOTHING_ASSETS: list[dict] = [
    {
        "name":       "Shirt",
        "mhclo":      _CLOTHING_DIR / "elvs_crude_t-shirt_male" / "elvs_crude_t-shirt_male.mhclo",
        "obj":        _CLOTHING_DIR / "elvs_crude_t-shirt_male" / "crude_male_shirt.obj",
        "color":      (0.85, 0.82, 0.78, 1.0),
        "max_z_frac": None,
    },
    {
        "name":       "Pants",
        "mhclo":      _CLOTHING_DIR / "toigo_wool_pants" / "toigo_wool_pants.mhclo",
        "obj":        _CLOTHING_DIR / "toigo_wool_pants" / "pants_wool.obj",
        "color":      (0.22, 0.27, 0.35, 1.0),
        "max_z_frac": 0.52,
    },
]


def _get_mpfb_service(class_path: str) -> type | None:
    """Resolve an MPFB service through the module cached by character.py."""
    import sys
    # Import lazily to avoid circular dependency — character.py sets _MPFB_MOD.
    from campo.blender import character as _char_mod
    obj: object | None = _char_mod._MPFB_MOD
    if obj is None:
        return None
    for part in class_path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj  # type: ignore[return-value]


def _ensure_material(clothing: bpy.types.Object, color: tuple[float, float, float, float]) -> None:
    for slot in clothing.material_slots:
        if slot.material is not None:
            slot.material.diffuse_color = color
            return
    mat = bpy.data.materials.new(name=f"{clothing.name}_Mat")
    mat.diffuse_color = color
    clothing.data.materials.append(mat)


def _mpfb_fit(
    actor: bpy.types.Object,
    mhclo_path: Path,
    obj_path: Path,
    name: str,
) -> bpy.types.Object | None:
    """Import OBJ then reposition via MPFB ClothesService.fit_clothes_to_human."""
    ClothesService = _get_mpfb_service("services.clothesservice.ClothesService")
    if ClothesService is None:
        return None

    keys_before = set(bpy.data.objects.keys())
    try:
        bpy.ops.wm.obj_import(filepath=str(obj_path))
    except Exception as exc:
        logger.warning("wm.obj_import failed for '%s': %s", obj_path.name, exc)
        return None

    new_keys = set(bpy.data.objects.keys()) - keys_before
    if not new_keys:
        return None

    clothing = bpy.data.objects[next(iter(new_keys))]
    clothing.name = name

    try:
        Mhclo = _get_mpfb_service("entities.clothes.mhclo.Mhclo")
        mhclo = Mhclo()
        mhclo.load(str(mhclo_path))
        mhclo.clothes = clothing
        ClothesService.fit_clothes_to_human(clothing, actor, mhclo)
        logger.info("Clothing '%s' fitted via fit_clothes_to_human.", name)
        return clothing
    except Exception as exc:
        logger.warning("fit_clothes_to_human failed for '%s': %s", name, exc)
        bpy.data.objects.remove(clothing, do_unlink=True)
        return None


def _obj_scale_fit(
    actor: bpy.types.Object,
    obj_path: Path,
    name: str,
    max_z_frac: float | None = None,
) -> bpy.types.Object | None:
    """
    Import OBJ and rescale to fit the actor using actor_height / 7.5 scale factor.
    Vertices above max_z_frac * actor_height are clipped via bmesh (used for pants).
    """
    keys_before = set(bpy.data.objects.keys())
    try:
        bpy.ops.wm.obj_import(filepath=str(obj_path))
    except Exception as exc:
        logger.warning("wm.obj_import failed for '%s': %s", obj_path.name, exc)
        return None

    new_keys = set(bpy.data.objects.keys()) - keys_before
    if not new_keys:
        return None

    clothing = bpy.data.objects[next(iter(new_keys))]
    clothing.name = name

    actor_corners = [actor.matrix_world @ Vector(c) for c in actor.bound_box]
    actor_height  = max(v.z for v in actor_corners) - min(v.z for v in actor_corners)
    scale = actor_height / 7.5
    clothing.scale = (scale, scale, scale)
    bpy.context.view_layer.update()

    cloth_corners = [clothing.matrix_world @ Vector(c) for c in clothing.bound_box]
    z_min = min(v.z for v in cloth_corners)
    if z_min < 0.0:
        clothing.location.z -= z_min

    clothing.location.x = actor.location.x
    clothing.location.y = actor.location.y

    if max_z_frac is not None:
        z_clip_world = actor_height * max_z_frac
        z_clip_local = (z_clip_world - clothing.location.z) / scale
        bm = bmesh.new()
        bm.from_mesh(clothing.data)
        to_delete = [v for v in bm.verts if v.co.z > z_clip_local]
        bmesh.ops.delete(bm, geom=to_delete, context="VERTS")
        bm.to_mesh(clothing.data)
        bm.free()
        clothing.data.update()
        logger.info("Clothing '%s' clipped at world Z=%.3fm.", name, z_clip_world)

    logger.info(
        "Clothing '%s' loaded via OBJ scale-fit (scale=%.4f).", name, scale,
    )
    return clothing


def add_clothing(actor: bpy.types.Object) -> list[bpy.types.Object]:
    """Attach bundled shirt and pants to the actor."""
    loaded: list[bpy.types.Object] = []
    for asset in _CLOTHING_ASSETS:
        name: str = asset["name"]
        clothing = _obj_scale_fit(actor, asset["obj"], name, asset.get("max_z_frac"))
        if clothing is not None:
            _ensure_material(clothing, asset["color"])
            loaded.append(clothing)
        else:
            logger.warning("Could not load clothing '%s' — skipping.", name)
    logger.info("Clothing attached: %s", [o.name for o in loaded])
    return loaded
