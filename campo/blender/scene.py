"""
Top-level scene orchestrator for the Campo storyboard pipeline.

build_scene() is the single entry point that composes all sub-modules:
character loading → floor → camera → render config → render trigger.
"""

import logging
from pathlib import Path

import bpy

from campo.schema import SceneRequest
from campo.blender.camera import setup_camera
from campo.blender.character import (
    add_rig_to_human,
    ensure_skin_material,
    load_blend_character,
    load_mpfb_human_service,
    pose_arms_at_side,
    pose_arms_natural,
    spawn_human,
)
from campo.blender.clothing import add_clothing
from campo.blender.render import configure_render

logger = logging.getLogger(__name__)

# Character blend file — Rain is preferred when present; falls back to person.blend.
_ASSETS: Path = Path(__file__).resolve().parent.parent.parent / "assets"
_CHAR_BLEND: Path = (
    _ASSETS / "Rain v3.3" / "rain_v3.2.blend"
    if (_ASSETS / "Rain v3.3" / "rain_v3.2.blend").exists()
    else _ASSETS / "person.blend"
)


def clear_scene() -> None:
    """Remove all objects, meshes, cameras, and lights using data-block access."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for cam in list(bpy.data.cameras):
        bpy.data.cameras.remove(cam)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)
    logger.info("Scene cleared.")


def add_floor() -> bpy.types.Object:
    """Add a 6 m × 6 m ground plane via bmesh — no ops required."""
    import bmesh as _bmesh
    mesh = bpy.data.meshes.new("Floor_Mesh")
    bm   = _bmesh.new()
    _bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3.0)  # size = half-extent
    bm.to_mesh(mesh)
    bm.free()
    floor = bpy.data.objects.new("Floor", mesh)
    bpy.context.scene.collection.objects.link(floor)
    logger.info("Floor added.")
    return floor


def build_scene(request: SceneRequest = SceneRequest()) -> None:
    """
    Build and render a single storyboard frame from a SceneRequest.

    Character path:
      - If assets/person.blend exists, load_blend_character() is used (fast).
      - Otherwise, MPFB is spawned programmatically (slower, requires MPFB addon).
    """
    if _CHAR_BLEND.exists():
        actor = load_blend_character(_CHAR_BLEND)
        pose_arms_at_side(actor)
    else:
        clear_scene()
        HumanService = load_mpfb_human_service()
        actor        = spawn_human(HumanService)
        add_rig_to_human(actor)
        pose_arms_natural(actor)
        ensure_skin_material(actor)
        add_clothing(actor)

    add_floor()
    setup_camera(actor, request)
    configure_render(request.render)

    logger.info("Rendering → %s", request.render.output_path)
    bpy.ops.render.render(write_still=True)
    logger.info("Frame saved: %s", request.render.output_path)
