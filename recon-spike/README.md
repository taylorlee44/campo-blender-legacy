# recon-spike — Phase A quality proof

**Throwaway spike.** Its only job is to answer the **M0 gate** in
`docs/reconstruction_roadmap.md`: *does server-side gsplat match Scaniverse on a real
room, and does a photoreal backdrop make storyboards meaningfully better?*

This is **not** the owned reconstruction pipeline. That is M2 (`campo-reconstruct`, a
separate repo, Modal/CUDA). Keep this spike self-contained and **delete it once M0 is
decided** — do not let it grow into the production service inside this repo.

---

## What's here

| File | Role |
|---|---|
| `capture_schema.py` | Capture-bundle dataclasses + validator. Doubles as the concrete reference the iOS side mirrors until M1 freezes the real contract. |
| `reconstruct.py` | Driver: frames bundle → hosted gsplat model → `.ply` splat. |
| `viewer/index.html` | Standalone two-pane Spark viewer to A/B two splats. No server, no Next.js. |
| `sample_capture/capture.json` | Schema example (structure only — no images). |

## The M0 protocol

1. **Capture one room two ways, same lighting:**
   - **Scaniverse** scan → export `.ply`/`.spz` (the reference).
   - **iOS spike bundle** — ~100–200 frames + `capture.json` (poses, intrinsics, gravity).
     Schema: `capture_schema.py`. (Until the iOS spike exists, a manual capture with
     COLMAP-derived poses is a stand-in — it validates baseline quality but **not** the
     ARKit-poses-skip-SfM win.)
2. **Reconstruct** the bundle:
   ```bash
   pip install -r recon-spike/requirements.txt
   export REPLICATE_API_TOKEN=...
   export RECON_MODEL=owner/model:version      # see candidates below
   python recon-spike/reconstruct.py path/to/bundle --out out/recon
   ```
3. **A/B** in `viewer/index.html` — open it, load the Scaniverse splat on the left and the
   gsplat output on the right, compare fidelity + geometry. (`out/` is gitignored.)
4. **Storyboard test** (the half that needs the real app): judge whether the photoreal
   backdrop improves generated frames vs a gray-box room. Known chicken-and-egg — the web
   tool can't load a *splat* env until M3 (Spark integration). For M0, either judge
   visually, or run a one-off splat→mesh (SuGaR) and load the `.glb` via the existing env
   import. Don't build M3 to answer M0.
5. **Decide & record** in the roadmap: go/no-go · splat-vs-mesh primary · per-scene-vs-feed-forward latency.

## RECON_MODEL candidates

No canonical Replicate gsplat slug is hardcoded (they drift). Pick one and confirm its
input schema, then adapt `_build_model_input` in `reconstruct.py`:
- Search Replicate for a `gaussian-splatting` / `gsplat` trainer (images/video → `.ply`).
- Most hosted trainers re-run COLMAP and **ignore supplied poses** → fine for baseline
  quality, but to prove the ARKit-pose win you need a pose-accepting endpoint or a quick
  gsplat run on RunPod/Modal.

## Known gaps (don't trust results past these)

- **Pose handling:** see above — baseline-quality only unless poses are honored.
- **Spark API drift:** `viewer/index.html` uses unpinned esm.sh imports following Spark's
  documented shape. Verify against current Spark docs and pin versions before relying on it.
- **Format:** driver saves `.ply`; convert to `.spz` for web later (M3 concern, not M0).
