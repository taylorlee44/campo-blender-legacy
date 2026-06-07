"""
Export three pre-configured storyboard reference frames in a single Blender session.

Builds the character once, then swaps the camera for each shot — faster than
calling build_scene() three times because the MPFB spawn / blend load only runs once.

Usage:
    blender -b assets/person.blend -P scripts/export_shots.py
"""

import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.__stdout__,
)

import bpy  # noqa: E402

from campo.blender.camera import setup_camera
from campo.blender.character import load_blend_character
from campo.blender.render import configure_render
from campo.blender.scene import add_floor
from campo.schema import CameraAngle, CameraHeight, RenderConfig, SceneRequest, ShotSize

OUTPUT_DIR = Path.home() / "Desktop" / "storyboard_export"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SHOTS: list[SceneRequest] = [
    SceneRequest(
        shot_size=ShotSize.CU,
        camera_angle=CameraAngle.FRONT,
        camera_height=CameraHeight.EYE_LEVEL,
        render=RenderConfig(output_path=str(OUTPUT_DIR / "01_CU_frontal.png")),
    ),
    SceneRequest(
        shot_size=ShotSize.WS,
        camera_angle=CameraAngle.PROFILE_LEFT,
        camera_height=CameraHeight.EYE_LEVEL,
        render=RenderConfig(output_path=str(OUTPUT_DIR / "02_WS_profile.png")),
    ),
    SceneRequest(
        shot_size=ShotSize.MS,
        camera_angle=CameraAngle.THREE_QUARTER_LEFT,
        camera_height=CameraHeight.EYE_LEVEL,
        render=RenderConfig(output_path=str(OUTPUT_DIR / "03_MS_three_quarter.png")),
    ),
]

_CHAR_BLEND = _REPO_ROOT / "assets" / "person.blend"

logger = logging.getLogger(__name__)


def export_shots() -> None:
    actor = load_blend_character(_CHAR_BLEND)
    add_floor()

    for request in SHOTS:
        # Remove any existing camera before placing the next one.
        for obj in list(bpy.data.objects):
            if obj.type == "CAMERA":
                bpy.data.objects.remove(obj, do_unlink=True)

        setup_camera(actor, request)
        configure_render(request.render)
        bpy.ops.render.render(write_still=True)
        logger.info("Saved: %s", request.render.output_path)


export_shots()
