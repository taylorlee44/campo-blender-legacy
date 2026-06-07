"""
Batch render a grid of storyboard frames (all angles × all shot sizes).

Produces one PNG per combination — 6 angles × 7 sizes = 42 frames — to
~/Desktop/storyboard_batch/. Useful for reviewing the full vocabulary coverage
and for building reference datasets.

Usage:
    blender -b assets/person.blend -P scripts/render_batch.py
"""

import logging
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

OUTPUT_DIR = Path.home() / "Desktop" / "storyboard_batch"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_CHAR_BLEND = _REPO_ROOT / "assets" / "person.blend"

logger = logging.getLogger(__name__)


def render_batch() -> None:
    actor = load_blend_character(_CHAR_BLEND)
    add_floor()

    total = len(CameraAngle) * len(ShotSize)
    count = 0

    for angle in CameraAngle:
        for size in ShotSize:
            count += 1
            filename = f"{angle.value}_{size.value}.png"
            request = SceneRequest(
                shot_size=size,
                camera_angle=angle,
                camera_height=CameraHeight.EYE_LEVEL,
                render=RenderConfig(output_path=str(OUTPUT_DIR / filename)),
            )

            for obj in list(bpy.data.objects):
                if obj.type == "CAMERA":
                    bpy.data.objects.remove(obj, do_unlink=True)

            setup_camera(actor, request)
            configure_render(request.render)
            bpy.ops.render.render(write_still=True)
            logger.info("[%d/%d] Saved: %s", count, total, filename)


render_batch()
