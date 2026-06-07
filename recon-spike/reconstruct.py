"""Phase A reconstruction driver — frames bundle -> Gaussian splat (.ply/.spz).

THROWAWAY SPIKE. Its only job is to answer the M0 gate: does server-side gsplat
match Scaniverse on a real room? It rents a hosted model for an afternoon; it is
NOT the owned pipeline (that is M2, in the campo-reconstruct repo).

Usage:
    export REPLICATE_API_TOKEN=...
    export RECON_MODEL=owner/model:version   # see README for candidates
    python recon-spike/reconstruct.py path/to/bundle --out out/recon

Notes / known gaps (read README before trusting results):
  * Most hosted gsplat models re-run COLMAP SfM and IGNORE supplied poses, so
    this validates baseline splat quality but NOT the ARKit-poses-skip-SfM win.
    Confirming that win needs a pose-accepting endpoint or our own gsplat run.
  * The model input schema varies per model; _build_model_input is the one spot
    to adapt to whichever RECON_MODEL we pick.
"""

from __future__ import annotations

import argparse
import logging
import os
import zipfile
from pathlib import Path

from capture_schema import load_capture, validate

logger = logging.getLogger(__name__)


def _zip_frames(bundle_dir: Path, capture, out_zip: Path) -> Path:
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for fr in capture.frames:
            zf.write(bundle_dir / fr.file, arcname=Path(fr.file).name)
    logger.info("zipped %d frames -> %s", len(capture.frames), out_zip)
    return out_zip


def _build_model_input(frames_zip: Path) -> dict[str, object]:
    """Adapt to the chosen RECON_MODEL's input schema. Default: a zip of images."""
    return {"images": open(frames_zip, "rb")}


def reconstruct(bundle_dir: Path, out_dir: Path) -> Path:
    import replicate

    model = os.environ.get("RECON_MODEL")
    if not model:
        raise SystemExit(
            "RECON_MODEL is unset. Pick a hosted gsplat model (see recon-spike/README.md) "
            "and export RECON_MODEL=owner/model:version."
        )

    capture = load_capture(bundle_dir)
    validate(capture, bundle_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    frames_zip = _zip_frames(bundle_dir, capture, out_dir / f"{bundle_dir.name}_frames.zip")

    logger.info("submitting to %s ...", model)
    output = replicate.run(model, input=_build_model_input(frames_zip))

    out_path = out_dir / f"{bundle_dir.name}.ply"
    out_path.write_bytes(output.read() if hasattr(output, "read") else bytes(output))
    logger.info("splat written -> %s", out_path)
    return out_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="capture bundle dir (capture.json + frames/)")
    parser.add_argument("--out", type=Path, default=Path("out/recon"), help="output dir")
    args = parser.parse_args()
    reconstruct(args.bundle, args.out)


if __name__ == "__main__":
    main()
