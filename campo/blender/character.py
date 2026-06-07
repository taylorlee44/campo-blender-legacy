"""
Character management for the Campo storyboard pipeline.

Handles two character paths:
  1. Pre-built blend file (fast, default) — loaded via bpy.data.libraries or
     detected as already scene-resident when Blender opens person.blend as -b.
  2. MPFB live spawn (fallback) — generates a parametric human via MakeHuman
     Plugin for Blender, adds a rig, and poses the arms to T-pose.

MPFB runs as a Blender extension (bl_ext.blender_org.mpfb or
bl_ext.user_default.mpfb). All service access goes through the _MPFB_MOD
module cache to avoid bare "import mpfb" which always fails in extension context.
"""

import logging
import math
import sys

import addon_utils
import bmesh
import bpy
from mathutils import Euler, Vector

logger = logging.getLogger(__name__)

# Cached MPFB extension module, set by load_mpfb_human_service().
_MPFB_MOD: object | None = None

# Workbench fallback skin color used when MPFB has not assigned a material.
_SKIN_COLOR: tuple[float, float, float, float] = (0.8, 0.6, 0.5, 1.0)


# ── MPFB Discovery ────────────────────────────────────────────────────────────

def _get_mpfb_service(class_path: str) -> type | None:
    """
    Resolve an MPFB service class through the cached module.
    class_path is dot-separated from the module root, e.g.
    "services.targetservice.TargetService".
    """
    obj: object | None = _MPFB_MOD
    if obj is None:
        return None
    for part in class_path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj  # type: ignore[return-value]


def load_mpfb_human_service() -> type:
    """
    Locate and enable MPFB regardless of install path (legacy addon or
    Blender 5.x extensions). Sets _MPFB_MOD for subsequent service lookups.
    Returns the HumanService class.
    """
    global _MPFB_MOD
    module_name: str | None = None

    for addon in addon_utils.modules():
        if addon.__name__.endswith("mpfb"):
            module_name = addon.__name__
            addon_utils.enable(module_name, default_set=True)
            logger.info("MPFB found and enabled: %s", module_name)
            break

    if not module_name:
        try:
            addon_utils.enable("mpfb", default_set=True)
            module_name = "mpfb"
            logger.info("MPFB enabled via fallback name.")
        except Exception as exc:
            raise ImportError(
                "MPFB could not be activated. Go to Edit → Preferences → Extensions, "
                f"find MPFB, and make sure it is installed and checked.\nOriginal error: {exc}"
            )

    mpfb_mod = sys.modules.get(module_name)
    if mpfb_mod and hasattr(mpfb_mod, "services"):
        _MPFB_MOD = mpfb_mod
        return mpfb_mod.services.humanservice.HumanService
    else:
        from mpfb.services.humanservice import HumanService  # type: ignore[import]
        return HumanService


# ── Human Spawner ─────────────────────────────────────────────────────────────

def _default_macro_dict() -> dict:
    """
    Build the MPFB macro dict starting from MPFB's own defaults so future keys
    added by MPFB don't break the call. Falls back to a hardcoded dict when
    TargetService isn't available yet.
    """
    TargetService = _get_mpfb_service("services.targetservice.TargetService")
    if TargetService is not None:
        base = TargetService.get_default_macro_info_dict()
    else:
        base = {
            "gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5,
            "height": 0.5, "proportions": 0.5, "cupsize": 0.5, "firmness": 0.5,
            "race": {"asian": 0.33, "caucasian": 0.33, "african": 0.33},
        }
    base.update({
        "gender":      1.0,  # male
        "age":         0.3,  # ~22 years (0=child · 0.3=young adult · 1.0=elderly)
        "muscle":      0.5,
        "weight":      0.5,
        "height":      0.5,
        "proportions": 0.5,
    })
    return base


def spawn_human(HumanService: type, macro_detail_dict: dict | None = None) -> bpy.types.Object:
    """
    Spawn an MPFB human figure with macro details applied at creation time.

    create_human(macro_detail_dict=...) stores values as mesh custom properties
    and calls TargetService.reapply_macro_details() internally — no separate
    apply step needed.

    A seed mesh object is created via bpy.data (not ops) so MPFB's internal
    scene checks have a valid active object in headless context.
    """
    if macro_detail_dict is None:
        macro_detail_dict = _default_macro_dict()

    seed_mesh = bpy.data.meshes.new("_seed")
    bm = bmesh.new()
    bm.verts.new((0.0, 0.0, 0.0))
    bm.to_mesh(seed_mesh)
    bm.free()
    temp_obj = bpy.data.objects.new("_seed", seed_mesh)
    bpy.context.scene.collection.objects.link(temp_obj)
    bpy.context.view_layer.objects.active = temp_obj

    logger.info("Spawning MPFB human with context override...")
    with bpy.context.temp_override(object=temp_obj, active_object=temp_obj):
        result = HumanService.create_human(macro_detail_dict=macro_detail_dict)

    bpy.data.objects.remove(temp_obj, do_unlink=True)
    bpy.context.view_layer.update()

    if isinstance(result, bpy.types.Object):
        actor = result
    elif "makehuman_human" in bpy.data.objects:
        actor = bpy.data.objects["makehuman_human"]
    else:
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        if not meshes:
            raise RuntimeError("MPFB finished but no mesh object found in scene.")
        actor = meshes[0]

    actor.name = "Storyboard_Actor"
    logger.info(
        "Actor placed: '%s' — gender=%.1f age=%.1f",
        actor.name,
        macro_detail_dict.get("gender", 0.0),
        macro_detail_dict.get("age", 0.0),
    )
    return actor


# ── Rig ───────────────────────────────────────────────────────────────────────

def _find_armature(actor: bpy.types.Object) -> bpy.types.Object | None:
    """
    Find the armature associated with actor, checking four possible layouts
    that MPFB uses across versions.
    """
    if actor.parent and actor.parent.type == "ARMATURE":
        return actor.parent

    child = next(
        (o for o in bpy.data.objects if o.type == "ARMATURE" and o.parent == actor),
        None,
    )
    if child:
        return child

    for mod in actor.modifiers:
        if mod.type == "ARMATURE" and mod.object:
            return mod.object

    return next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)


def add_rig_to_human(actor: bpy.types.Object) -> bool:
    """
    Add an MPFB game rig to the actor mesh. Returns True if an armature is
    present after the call.

    IMPORTANT: do NOT wrap bpy.ops.mpfb.add_standard_rig in temp_override.
    It internally calls bpy.ops.object.armature_add then reads bpy.context.object
    to get the new armature. A temp_override locks bpy.context.object to the mesh
    for the operator's entire duration, causing MPFB to assign the mesh as the
    armature object and crash on mesh.data.display_type.
    """
    if _find_armature(actor) is not None:
        logger.info("Rig already present on '%s' — skipping.", actor.name)
        return True

    bpy.context.view_layer.objects.active = actor
    actor.select_set(True)
    bpy.context.view_layer.update()

    try:
        bpy.ops.mpfb.add_standard_rig()
        bpy.context.view_layer.update()
        rig = _find_armature(actor)
        if rig:
            logger.info("Rig added: '%s'", rig.name)
            return True
        logger.warning("add_standard_rig ran but no armature found.")
    except Exception as exc:
        logger.warning("bpy.ops.mpfb.add_standard_rig failed: %s", exc)

    logger.warning(
        "Could not add rig to '%s' — arms will remain in T-pose.", actor.name,
    )
    return False


# ── Arm Pose ──────────────────────────────────────────────────────────────────

def pose_arms_natural(actor: bpy.types.Object) -> None:
    """
    Rotate upperarm01 bones to bring the arms from A-pose to near-horizontal
    so the T-pose clothing OBJs align correctly.

    The MPFB human spawns in A-pose (arms ~48° below horizontal). Rotating
    upperarm01 around its local Z by ±90° counters the droop.
    PoseBone rotations are pure bpy.data — fully headless-safe.
    """
    arm_obj = _find_armature(actor)
    if arm_obj is None:
        logger.warning("No armature found for '%s' — arm pose skipped.", actor.name)
        return

    _SHOULDER_NAMES = ["shoulder01", "shoulder"]
    _UPPERARM_NAMES = ["upperarm01", "upper_arm"]

    def _get_bone(names: list[str], side: str) -> bpy.types.PoseBone | None:
        for base in names:
            b = arm_obj.pose.bones.get(f"{base}{side}")
            if b is not None:
                return b
        return None

    for side, z_sign in [(".L", -1), (".R", 1)]:
        shoulder = _get_bone(_SHOULDER_NAMES, side)
        if shoulder:
            shoulder.rotation_mode  = "XYZ"
            shoulder.rotation_euler = Euler((0.0, math.radians(-8), 0.0), "XYZ")

        upperarm = _get_bone(_UPPERARM_NAMES, side)
        if upperarm:
            upperarm.rotation_mode  = "XYZ"
            upperarm.rotation_euler = Euler((0.0, 0.0, math.radians(z_sign * -90)), "XYZ")

    bpy.context.view_layer.update()
    logger.info("Arm pose applied to '%s'.", actor.name)


# ── Arm Pose — at side ───────────────────────────────────────────────────────

def _pose_rain_ik_arms(arm_obj: bpy.types.Object) -> bool:
    """
    Pose Rain/CloudRig arms at side via IK-Hand.L/R — the free control bones.

    Chain: IK-Hand.L (free) → STRETCH_TO on IK-Arm_Stretch.L →
    COPY_LOCATION tail=1.0 on IK-Hand_Loc.L → IK on IK-Forearm.L →
    COPY_TRANSFORMS on FK bones → CT-FK → STR → DEF mesh.

    Returns True when CloudRig-specific bones are present.
    """
    bones = arm_obj.pose.bones
    if bones.get("IK-Arm_Stretch.L") is None:
        return False

    shoulder_l = bones.get("IK-Upperarm.L")
    shoulder_r = bones.get("IK-Upperarm.R")

    def _move_bone_to(pb: bpy.types.PoseBone, target_arm: Vector) -> None:
        delta = target_arm - pb.bone.head_local
        pb.location = pb.bone.matrix_local.to_3x3().inverted() @ delta

    for side in ("L", "R"):
        hand = bones.get(f"IK-Hand.{side}")
        if hand is None:
            logger.warning("IK-Hand.%s not found", side)
            continue

        shoulder  = shoulder_l if side == "L" else shoulder_r
        cur_world = arm_obj.matrix_world @ hand.bone.head_local

        if shoulder is not None:
            shld    = shoulder.bone.head_local
            arm_len = (hand.bone.head_local - shld).length
            target_arm = Vector((shld.x, shld.y, shld.z - arm_len))
        else:
            x = 0.15 if side == "L" else -0.15
            target_arm = Vector((x, hand.bone.head_local.y, hand.bone.head_local.z - 0.416))
            arm_len = 0.416

        # Also move the pole target straight down so elbow tracks with the arm
        # rather than staying at its T-pose height and pulling the elbow outward.
        pole = bones.get(f"IK-Pole-Forearm.{side}")
        if pole is not None:
            pole_rest = pole.bone.head_local
            pole_target = Vector((pole_rest.x, pole_rest.y, pole_rest.z - arm_len))
            delta_pole  = pole_target - pole_rest
            pole.location = pole.bone.matrix_local.to_3x3().inverted() @ delta_pole

        _move_bone_to(hand, target_arm)
        logger.info(
            "IK-Hand.%s: world %s → %s  arm_len=%.3f",
            side,
            tuple(round(v, 3) for v in cur_world),
            tuple(round(v, 3) for v in arm_obj.matrix_world @ target_arm),
            arm_len,
        )

    return True


def _pose_rain_fingers(arm_obj: bpy.types.Object) -> None:
    """
    Apply a natural relaxed curl to Rain's CloudRig finger FK control bones.

    Rain naming: FK-Index1.L .. FK-Index3.L, FK-Thumb1.L .. FK-Thumb3.L, etc.
    Curl = rotation around the bone's local Z axis (perpendicular to the palm plane).
    """
    bones = arm_obj.pose.bones

    _FINGER_CURL = math.radians(38.0)
    _THUMB_CURL  = math.radians(25.0)
    _NAMES = [
        ("Index",  3, _FINGER_CURL),
        ("Middle", 3, _FINGER_CURL),
        ("Ring",   3, _FINGER_CURL),
        ("Pinky",  3, _FINGER_CURL),
        ("Thumb",  3, _THUMB_CURL),
    ]

    applied = 0
    for base, segs, curl in _NAMES:
        for seg in range(1, segs + 1):
            for side in ("L", "R"):
                pb = bones.get(f"FK-{base}{seg}.{side}")
                if pb is None:
                    continue
                pb.rotation_mode  = "XYZ"
                pb.rotation_euler = Euler((curl, 0.0, 0.0), "XYZ")
                applied += 1

    logger.info("Finger curl applied to %d segments.", applied)


def pose_arms_at_side(actor: bpy.types.Object) -> None:
    """
    Pose the character's arms to hang at the side.

    Tries Rain's CloudRig IK control approach first (IK-Arm_Stretch bones),
    then falls back to FK quaternion rotation for Rigify/UE4 rigs.
    """
    arm_obj = _find_armature(actor)
    if arm_obj is None:
        logger.warning("No armature found for '%s' — arm pose skipped.", actor.name)
        return

    if arm_obj.animation_data and arm_obj.animation_data.action:
        logger.info("Detaching action '%s' from armature.", arm_obj.animation_data.action.name)
        arm_obj.animation_data.action = None

    bpy.context.view_layer.update()

    if _pose_rain_ik_arms(arm_obj):
        _pose_rain_fingers(arm_obj)
        bpy.context.view_layer.update()
        logger.info("Arms and fingers posed for '%s'.", actor.name)
        return

    # FK fallback for UE4-style (Claudia) and standard Rigify rigs.
    bones = arm_obj.pose.bones

    def _point_down(pb: bpy.types.PoseBone) -> None:
        """Set pose rotation so bone Y points in world -Z (straight down).

        Uses the bone's own current evaluated world matrix (pb.matrix), which
        already incorporates the full parent chain state. This works for both
        root-level bones (upperarm) and child bones (lowerarm, hand) as long
        as the dep-graph is updated before each call so pb.matrix is current.

        Formula: target_local = pb.matrix^-1 @ world_down
        Gives the rotation (from rest-pose bone-Y) needed to point world -Z.
        """
        for c in pb.constraints:
            if c.type == "COPY_TRANSFORMS":
                c.mute = True

        target_local: Vector = (
            pb.matrix.inverted().to_3x3()
            @ Vector((0.0, 0.0, -1.0))
        ).normalized()
        pb.rotation_mode       = "QUATERNION"
        pb.rotation_quaternion = Vector((0.0, 1.0, 0.0)).rotation_difference(target_local)

    # Bone name candidates: try CloudRig FK names first, then UE4/generic names.
    _UPPER = [("FK-Upperarm.L", "FK-Upperarm.R"), ("upperarm_l", "upperarm_r")]
    _LOWER = [("lowerarm_l", "lowerarm_r"), ("FK-Lowerarm.L", "FK-Lowerarm.R")]
    _HAND  = [("hand_l",      "hand_r"),     ("FK-Hand.L",      "FK-Hand.R")]

    def _find_pair(candidates: list[tuple[str, str]]) -> tuple[str, str] | None:
        return next((p for p in candidates if bones.get(p[0]) is not None), None)

    upper_pair = _find_pair(_UPPER)
    lower_pair = _find_pair(_LOWER)
    hand_pair  = _find_pair(_HAND)

    if upper_pair is None:
        logger.warning("No upper-arm bones found for '%s' — arm pose skipped.", actor.name)
        return

    # Pose each segment top-down, flushing the dep-graph between layers so
    # each child bone's pb.matrix reflects the parent's new rotation.
    for bone_name in upper_pair:
        pb = bones.get(bone_name)
        if pb is None:
            logger.warning("Bone '%s' not found.", bone_name)
            continue
        _point_down(pb)

    bpy.context.scene.frame_set(bpy.context.scene.frame_current)

    if lower_pair:
        for bone_name in lower_pair:
            pb = bones.get(bone_name)
            if pb is None:
                continue
            _point_down(pb)

        bpy.context.scene.frame_set(bpy.context.scene.frame_current)

    if hand_pair:
        for bone_name in hand_pair:
            pb = bones.get(bone_name)
            if pb is None:
                continue
            _point_down(pb)

        bpy.context.scene.frame_set(bpy.context.scene.frame_current)

    logger.info("Arms posed at side via FK for '%s'.", actor.name)


# ── Skin Material ─────────────────────────────────────────────────────────────

def ensure_skin_material(actor: bpy.types.Object) -> bpy.types.Material:
    """
    Ensure the actor has a skin-toned diffuse_color for Workbench MATERIAL mode.
    If MPFB already assigned a material it is left untouched.
    """
    for slot in actor.material_slots:
        if slot.material is not None:
            logger.info("MPFB material '%s' present — skin fallback skipped.", slot.material.name)
            return slot.material

    mat = bpy.data.materials.new(name="Skin_Fallback")
    mat.diffuse_color = _SKIN_COLOR
    actor.data.materials.append(mat)
    logger.info("Skin fallback material applied.")
    return mat


# ── Pre-built Blend Character ─────────────────────────────────────────────────

def load_blend_character(blend_path: "Path") -> bpy.types.Object:  # type: ignore[name-defined]
    """
    Return the pre-built character mesh from a .blend file.

    Two paths:
      1. Scene-resident (fast) — character is already present because Blender
         was launched with person.blend as the base file (-b flag).
      2. Library import (fallback) — appends objects via bpy.data.libraries.load.
         Startup objects (Cube, Camera, Light) are hidden from render rather than
         removed, because remove() triggers the 3D-Agent hook recursion in Blender 5.x.

    bpy.ops.wm.open_mainfile is intentionally avoided — it re-executes the -P
    script on every file load, causing infinite recursion.
    """
    from pathlib import Path as _Path

    def _hide(obj: bpy.types.Object) -> None:
        obj.hide_render   = True
        obj.hide_viewport = True

    for col in bpy.data.collections:
        col.hide_render   = False
        col.hide_viewport = False
    for vlc in bpy.context.view_layer.layer_collection.children:
        vlc.hide_viewport = False
        vlc.exclude       = False

    # If blend_path is the currently open file, all objects are already scene-resident.
    # bpy.data.libraries.load() cannot load from the current file, so skip it.
    is_current_file = _Path(bpy.data.filepath).resolve() == _Path(blend_path).resolve()

    actor = bpy.data.objects.get("rp_claudia_rigged_002_geo")
    if actor and actor.type == "MESH":
        for obj in bpy.data.objects:
            if obj.name.startswith("WGT-") or obj.name.endswith(".001"):
                _hide(obj)
        logger.info("Using scene-resident character '%s'.", actor.name)
        return actor

    if not is_current_file:
        with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
            data_to.objects = [n for n in data_from.objects if not n.startswith("WGT-")]

        for obj in data_to.objects:
            if obj is None:
                continue
            bpy.context.scene.collection.objects.link(obj)
            if obj.type == "MESH" and obj.name.endswith(".001"):
                _hide(obj)

        for name in ("Cube", "Camera", "Light"):
            obj = bpy.data.objects.get(name)
            if obj:
                _hide(obj)

        bpy.context.view_layer.update()

    # Hide rig widgets present in scene-resident files (e.g. Rain).
    for obj in bpy.data.objects:
        if obj.name.startswith("WGT-"):
            _hide(obj)

    actor = bpy.data.objects.get("rp_claudia_rigged_002_geo")
    if actor is None or actor.type != "MESH":
        skip   = {"Cube", "Camera", "Light"}
        meshes = [
            o for o in bpy.data.objects
            if o.type == "MESH"
            and not o.name.startswith("WGT-")
            and not o.name.endswith(".001")
            and o.name not in skip
        ]
        if not meshes:
            raise RuntimeError(f"No character mesh found in '{blend_path.name}'.")

        def _bbox_vol(obj: bpy.types.Object) -> float:
            corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            xs = [v.x for v in corners]
            ys = [v.y for v in corners]
            zs = [v.z for v in corners]
            return (max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs))

        actor = max(meshes, key=_bbox_vol)

    logger.info("Loaded character '%s' from '%s'.", actor.name, blend_path.name)
    return actor
