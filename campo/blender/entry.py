"""
Campo Blender pipeline — headless entry point.

This is the file Blender executes via the -P flag. It adds the repo root to
sys.path so the campo package is importable, then reads the SceneRequest from
--params-file (if provided) and delegates to build_scene().

Usage:
    # Default params (local dev, writes ~/Desktop/storyboard_frame.png):
    blender -b assets/person.blend -P campo/blender/entry.py

    # Parameterised (CI, fal.ai, iOS pipeline):
    blender -b assets/person.blend -P campo/blender/entry.py -- \\
        --params-file /tmp/params.json

    Example params.json (all fields optional):
    {
      "shot_size":     "CU",
      "camera_angle":  "THREE_QUARTER_LEFT",
      "camera_height": "HIGH_ANGLE",
      "lens_mm":       35.0,
      "render": {
        "output_path":  "/tmp/frame.png",
        "resolution_x": 1920,
        "resolution_y": 1080
      }
    }

Blender executes scripts at module level — no __main__ guard is used here.
Set CAMPO_NO_AUTORUN=1 in the environment to suppress auto-execution when
importing this file from another script (e.g. scripts/render_batch.py).
"""

import logging
import os
import sys
from pathlib import Path

# Add repo root to sys.path so `import campo` resolves inside Blender's Python.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Blender headless replaces sys.stdout/stderr with custom wrappers that feed
# back into Blender's log buffer — using them as logging targets creates an
# infinite output-capture loop. sys.__stdout__ is Python's original stream.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.__stdout__,
)

from campo.schema import load_params          # noqa: E402 — must come after sys.path setup
from campo.blender.scene import build_scene   # noqa: E402

if not os.environ.get("CAMPO_NO_AUTORUN"):
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    build_scene(load_params(_argv))
