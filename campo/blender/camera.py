"""
Camera placement for the Campo storyboard pipeline.

Shot framing is driven by ShotSize (what portion of the actor fills the frame)
combined with CameraAngle and CameraHeight (where the camera orbits). All
degree values come from campo.resolver — no raw numbers appear here.
"""

import logging
import math

import bpy
from mathutils import Vector

from campo.resolver import resolve_azimuth, resolve_elevation
from campo.schema import SceneRequest

logger = logging.getLogger(__name__)

# Super 35 horizontal sensor width — optical constant, not a user-facing param.
_SENSOR_WIDTH_MM: float = 24.89

# Framing table: (frame_bottom_frac, frame_top_frac) as proportion of actor height.
# 0.0 = feet, 1.0 = crown. Values outside [0, 1] add breathing room below/above.
#
# NOTE: This Blender path is dormant — the active path is campo/smpl/scene.py.
# The canonical framing values and shot size vocabulary live there and in
# campo/schema.py. This table is out of date (uses old MW/EWS names and pre-2026
# numeric values) and should be updated before this path is revived.
# See docs/blender.md and docs/shot_vocabulary.md.
_SHOT_FRAMING: dict[str, tuple[float, float]] = {
    "XCU": (0.855, 0.980),  # lips to mid-forehead
    "CU":  (0.795, 1.02),   # head and shoulders
    "MCU": (0.72,  1.06),   # chest/collarbone up
    "MS":  (0.50,  1.06),   # waist up
    "MWS": (0.28,  1.06),   # knees up
    "WS":  (-0.05, 1.09),   # full body with headroom
    "XWS": (-0.45, 1.30),   # character small in frame
}


def setup_camera(actor: bpy.types.Object, request: SceneRequest) -> bpy.types.Object:
    """
    Place and aim a camera for the given SceneRequest.

    Shot size determines the vertical crop (via _SHOT_FRAMING). Distance is
    derived from the crop height and lens FOV — never hardcoded. Azimuth and
    elevation come from the resolver, keeping degree values out of user-facing
    code. Rotation uses to_track_quat so no manual Euler angles are needed.
    """
    corners     = [actor.matrix_world @ Vector(c) for c in actor.bound_box]
    min_z       = min(v.z for v in corners)
    max_z       = max(v.z for v in corners)
    actor_height = max_z - min_z

    focus_x = (min(v.x for v in corners) + max(v.x for v in corners)) / 2.0
    focus_y = (min(v.y for v in corners) + max(v.y for v in corners)) / 2.0

    bot_frac, top_frac = _SHOT_FRAMING[request.shot_size.value]
    frame_bot_z  = min_z + bot_frac * actor_height
    frame_top_z  = min_z + top_frac * actor_height
    frame_height = frame_top_z - frame_bot_z
    focus_z      = (frame_bot_z + frame_top_z) / 2.0

    # Distance so the framed region fills the vertical FOV exactly.
    aspect   = request.render.resolution_x / request.render.resolution_y
    sensor_h = _SENSOR_WIDTH_MM / aspect
    vfov     = 2.0 * math.atan(sensor_h / (2.0 * request.lens_mm))
    distance = frame_height / (2.0 * math.tan(vfov / 2.0))

    az = math.radians(resolve_azimuth(request.camera_angle))
    el = math.radians(resolve_elevation(request.camera_height))
    cam_pos = Vector((
        focus_x + math.sin(az) * math.cos(el) * distance,
        focus_y - math.cos(az) * math.cos(el) * distance,
        focus_z + math.sin(el) * distance,
    ))

    focus_point = Vector((focus_x, focus_y, focus_z))
    direction   = (focus_point - cam_pos).normalized()

    cam_data = bpy.data.cameras.new(name="Cinematic_Cam_Data")
    cam_obj  = bpy.data.objects.new(name="Cinematic_Camera", object_data=cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    cam_obj.location       = cam_pos
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    cam_data.lens         = request.lens_mm
    cam_data.sensor_fit   = "HORIZONTAL"
    cam_data.sensor_width = _SENSOR_WIDTH_MM

    bpy.context.scene.camera = cam_obj
    logger.info(
        "Camera: %s %s %s %.0fmm dist=%.2fm",
        request.shot_size.value,
        request.camera_angle.value,
        request.camera_height.value,
        request.lens_mm,
        distance,
    )
    return cam_obj
