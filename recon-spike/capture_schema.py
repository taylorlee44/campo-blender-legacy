"""Capture bundle schema + validator for the Phase A reconstruction proof.

This is the throwaway-spike mirror of the frames+poses upload contract. When M1
(Contract Lock) freezes the real contract, promote this into the shared spec and
delete the spike copy. Until then it doubles as the concrete reference the iOS
side mirrors in Codable structs.

Bundle layout on disk:
    <bundle>/
        capture.json        # the manifest validated here
        frames/0001.jpg ...  # the RGB frames referenced by manifest
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float


@dataclass
class Frame:
    file: str
    timestamp: float
    intrinsics: Intrinsics
    transform: list[list[float]]
    has_depth: bool


@dataclass
class Capture:
    version: int
    device: str
    world_frame: str
    gravity: list[float]
    image_width: int
    image_height: int
    frames: list[Frame]


class CaptureError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaptureError(message)


def load_capture(bundle_dir: Path) -> Capture:
    manifest = bundle_dir / "capture.json"
    _require(manifest.is_file(), f"missing capture.json in {bundle_dir}")
    raw = json.loads(manifest.read_text())

    frames = [
        Frame(
            file=f["file"],
            timestamp=float(f["timestamp"]),
            intrinsics=Intrinsics(**f["intrinsics"]),
            transform=f["transform"],
            has_depth=bool(f.get("has_depth", False)),
        )
        for f in raw["frames"]
    ]
    return Capture(
        version=int(raw["version"]),
        device=str(raw.get("device", "unknown")),
        world_frame=str(raw["world_frame"]),
        gravity=[float(v) for v in raw["gravity"]],
        image_width=int(raw["image_width"]),
        image_height=int(raw["image_height"]),
        frames=frames,
    )


def validate(capture: Capture, bundle_dir: Path) -> None:
    """Catch the contract footguns before we waste a GPU minute on them."""
    _require(capture.version == 1, f"unsupported capture version {capture.version}")
    _require(capture.world_frame == "arkit", f"unexpected world_frame {capture.world_frame!r}")
    _require(len(capture.frames) >= 20, f"only {len(capture.frames)} frames; want ~100-200")

    gnorm = math.sqrt(sum(v * v for v in capture.gravity))
    _require(abs(gnorm - 1.0) < 0.05, f"gravity is not a unit vector (|g|={gnorm:.3f})")

    for fr in capture.frames:
        img = bundle_dir / fr.file
        _require(img.is_file(), f"frame image not found: {fr.file}")
        _require(
            len(fr.transform) == 4 and all(len(row) == 4 for row in fr.transform),
            f"transform for {fr.file} is not 4x4 (must be camera-to-world)",
        )
        _require(
            0 < fr.intrinsics.cx < capture.image_width
            and 0 < fr.intrinsics.cy < capture.image_height,
            f"intrinsics principal point for {fr.file} is outside the image — "
            "are fx/fy/cx/cy in pixels for the EXPORTED resolution?",
        )

    logger.info(
        "capture OK: %d frames, %dx%d, device=%s",
        len(capture.frames),
        capture.image_width,
        capture.image_height,
        capture.device,
    )
