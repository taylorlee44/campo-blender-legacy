"""
Render configuration for the Campo storyboard pipeline.

Sets up Blender Workbench engine — fast, headless-safe, and produces clean
geometry reference suitable for ControlNet depth/lineart conditioning.
"""

import logging

import bpy

from campo.schema import RenderConfig

logger = logging.getLogger(__name__)


def configure_render(cfg: RenderConfig) -> None:
    """Apply render settings from RenderConfig to the active scene."""
    scene = bpy.context.scene

    scene.render.engine                     = "BLENDER_WORKBENCH"
    scene.display.shading.light             = "STUDIO"
    scene.display.shading.color_type        = "MATERIAL"
    scene.display.shading.show_shadows      = True

    scene.render.resolution_x               = cfg.resolution_x
    scene.render.resolution_y               = cfg.resolution_y
    scene.render.filepath                   = cfg.output_path  # bpy expects str
    scene.render.image_settings.file_format = "PNG"

    logger.info(
        "Render configured: %d×%d Workbench → %s",
        cfg.resolution_x, cfg.resolution_y, cfg.output_path,
    )
