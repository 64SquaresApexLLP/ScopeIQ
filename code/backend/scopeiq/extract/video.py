"""Drone orbit video -> sampled evidence frames.

Frames are sampled evenly across the orbit, scored for sharpness (variance of the Laplacian; blurred frames
score low) and tagged with the camera bearing and the sector facing the camera. The sharpest frames per sector
are marked `selected` and attached to discrepancies and redlines as visual evidence. Frames are evidence for a
reviewer, not measurements (labels are not legible). An optional vision-model hook (`describe_frame`) can be
plugged in, e.g. Snowflake Cortex AI_COMPLETE with an image, without changing the pipeline.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from scopeiq.common.errors import ExtractionError
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import VideoFrame

log = get_logger(__name__)


def orbit_bearing(frame_index: int, total: int, start_deg: float = 90.0, clockwise: bool = True) -> float:
    """Camera bearing for an orbit flight. Default matches the survey vendor's flight plan: the drone starts due
    east (90 deg) and orbits counter-clockwise seen from above (bearing decreasing)."""
    a = 360.0 * frame_index / max(total, 1)
    return (start_deg - a) % 360 if clockwise else (start_deg + a) % 360


@log_call()
def sample_frames(video: Path, out_dir: Path, *, site_id: str, n_frames: int = 24, sector_azimuths: dict[str, float] | None = None,
                  per_sector: int = 2, describe_frame: Callable[[Path], str] | None = None) -> list[VideoFrame]:
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ExtractionError(f"Video {Path(video).name} cannot be opened", details={"site_id": site_id})
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 12.0
    if total <= 0:
        raise ExtractionError("Video has no frames", details={"file": Path(video).name})
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    idxs = sorted({int(round(i * total / n_frames)) for i in range(n_frames)} - {total})
    frames: list[VideoFrame] = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, img = cap.read()
        if not ok:
            log.warning("frame %d unreadable", i, extra={"site_id": site_id})
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        b = orbit_bearing(i, total)
        sec = None
        if sector_azimuths:
            sec, az = min(sector_azimuths.items(), key=lambda kv: abs((b - kv[1] + 180) % 360 - 180))
            if abs((b - az + 180) % 360 - 180) > 60:
                sec = None
        path = out_dir / f"{site_id}_f{i:03d}.jpg"
        cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 82])
        frames.append(VideoFrame(i, round(i / fps, 2), round(b, 1), sec, round(sharp, 1), str(path)))
    cap.release()
    def off(f: VideoFrame) -> float:
        return abs((f.bearing_deg - (sector_azimuths or {}).get(f.sector, f.bearing_deg) + 180) % 360 - 180)

    for sec in {f.sector for f in frames if f.sector}:
        cands = [f for f in frames if f.sector == sec and off(f) <= 30] or [f for f in frames if f.sector == sec]
        for f in sorted(cands, key=lambda f: -f.sharpness)[:per_sector]:      # facing the sector, then sharpest
            f.selected = True
            if describe_frame:
                try:
                    log.info("vision note frame %d: %s", f.frame_index, describe_frame(Path(f.path)), extra={"site_id": site_id})
                except Exception as exc:  # noqa: BLE001 - optional hook must never fail the pipeline
                    log.warning("vision hook failed: %s", exc, extra={"site_id": site_id})
    log.info("video: %d frames sampled of %d, %d selected", len(frames), total, sum(f.selected for f in frames), extra={"site_id": site_id})
    return frames
