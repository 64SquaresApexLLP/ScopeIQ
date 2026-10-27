"""Proof for a redline: the drone footage that shows the place the redline is about.

A reviewer should not have to take a redline on trust, so each one carries the frame of the orbit video that looks at the issue
(and a drone still of the same side, when the survey has one). Nothing here is tied to a site: the choice comes from the media.

  1. Where to look. The finding's own drone object gives a bearing from the structure; failing that, the sector's objects or its
     design azimuth do. A site-wide finding has no direction, so the clearest view of the equipment is used.
  2. What the video shows. Every sampled frame has its camera bearing and a measure of how much equipment it shows (extract/video.py).
     A frame qualifies when it faces the place (within the tolerance) and shows the equipment; frames that cut the equipment off the
     edge, or show little of it, rank lower. A rising orbit that has not yet reached the equipment therefore never supplies proof.
  3. When the video has no such view (the orbit never faces that side at the equipment's height), a drone still looking at that side is
     used instead, and the proof says so. If nothing faces the place, the clearest overview is attached and labelled as an overview.

The picture is cropped to the equipment and captioned with where it came from, so the reviewer sees what was used and why.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings
from scopeiq.domain import SECTOR_NAMES, Discrepancy, Redline, SiteFacts

log = get_logger(__name__)


@dataclass
class Still:
    path: Path
    label: str                  # what the survey calls it, e.g. "Oblique sector view (Beta)"
    bearing_deg: float | None   # compass bearing of the camera as seen from the structure
    sector_view: bool           # a view of one side (as opposed to an overview)


@dataclass
class Proof:
    redline_id: str
    rank: int
    kind: str                   # VIDEO | IMAGE
    path: str                   # absolute while it is being written; the pipeline stores it relative to the output folder
    caption: str
    basis: str                  # why this picture was chosen
    sector: str | None = None
    time_s: float | None = None
    bearing_deg: float | None = None
    off_deg: float | None = None


def _off(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _mean_bearing(values: list[float]) -> float:
    return math.degrees(math.atan2(sum(math.sin(math.radians(v)) for v in values), sum(math.cos(math.radians(v)) for v in values))) % 360.0


def read_stills(meta_path: Path | None, images: dict[str, Path]) -> list[Still]:
    """The survey's stills with the side each one looks at, worked out from where its camera was placed."""
    if not meta_path or not Path(meta_path).exists():
        return []
    try:
        imagery = json.loads(Path(meta_path).read_text(encoding="utf-8")).get("imagery", [])
    except (OSError, ValueError):
        return []
    out = []
    for im in imagery:
        path, cam = images.get(im.get("file", "")), im.get("camera_xyz_m")
        if not path or not cam:
            continue                                                    # the orthomosaic has no side it faces
        at = im.get("look_at_m") or [0.0, 0.0, 0.0]
        bearing = math.degrees(math.atan2(cam[0] - at[0], cam[1] - at[1])) % 360.0
        out.append(Still(path, im.get("type", "Drone still"), round(bearing, 1), "sector" in im.get("type", "").lower()))
    return out


def _target(f: SiteFacts, d: Discrepancy) -> tuple[float | None, str]:
    """The bearing (seen from the structure) that the camera has to face to see what the finding is about."""
    sec, name = d.sector, SECTOR_NAMES.get(d.sector or "", d.sector or "")
    if not sec:
        return None, "a site-wide finding, so the clearest view of the equipment"
    objs = [o for o in f.field_objects if o.sector == sec and o.bearing_deg is not None]
    if d.position is not None:
        obj = next((o for o in objs if o.position == d.position), None)
        if obj:
            return obj.bearing_deg, f"the drone's {obj.object_type.lower()} at {name} position {d.position}"
    if objs:
        return _mean_bearing([o.bearing_deg for o in objs]), f"the {name} side of the structure"
    az = next(iter((f.sectors[sec].azimuth if sec in f.sectors else {}).values()), None)
    return (float(az), f"the {name} side of the structure (design azimuth)") if az is not None else (None, "a finding without a direction")


def choose(f: SiteFacts, d: Discrepancy, stills: list[Still]) -> list[dict]:
    """Up to `engine.proof_per_redline` pictures: the best video frame, then a drone still of the same side or the next video frame."""
    st = get_settings()
    tol, limit = float(st.get("engine.proof_max_angle_deg", 45)), int(st.get("engine.proof_per_redline", 2))
    target, what = _target(f, d)
    peak = max((fr.equipment for fr in f.frames), default=0.0)
    out: list[dict] = []

    def cost(fr) -> float:
        return (0.0 if target is None else _off(fr.bearing_deg, target) / tol) + 0.6 * (1 - fr.equipment / peak) + (0.5 if fr.clipped else 0.0)

    seen = [fr for fr in f.frames if peak and fr.equipment >= 0.4 * peak and fr.box]
    facing = sorted((fr for fr in seen if target is None or _off(fr.bearing_deg, target) <= tol), key=cost)
    if facing:
        out.append({"kind": "VIDEO", "frame": facing[0], "off": None if target is None else _off(facing[0].bearing_deg, target), "what": what})
    side = sorted((s for s in stills if s.sector_view and target is not None and s.bearing_deg is not None and _off(s.bearing_deg, target) <= 60),
                  key=lambda s: _off(s.bearing_deg, target))
    if side:
        out.append({"kind": "IMAGE", "still": side[0], "off": _off(side[0].bearing_deg, target), "what": what,
                    "why": "the video does not face this side at the height of the equipment" if not facing else "a clearer still of the same side"})
    elif len(facing) > 1 and target is not None:                       # a site-wide finding needs one clear view, not two of the same
        second = next((fr for fr in facing[1:] if _off(fr.bearing_deg, facing[0].bearing_deg) >= 12), None)
        if second:
            out.append({"kind": "VIDEO", "frame": second, "off": None if target is None else _off(second.bearing_deg, target), "what": what})
    if not out and seen:                                                # nothing faces the place: the clearest overview, labelled as one
        best = min(seen, key=lambda fr: (0.0 if fr.clipped is False else 1.0, -fr.equipment))
        out.append({"kind": "VIDEO", "frame": best, "off": None if target is None else _off(best.bearing_deg, target), "what": what, "overview": True})
    return out[:limit]


def _caption(c: dict, d: Discrepancy) -> tuple[str, str]:
    where = f"{SECTOR_NAMES.get(d.sector or '', d.sector or 'Site')}" + (f" position {d.position}" if d.position is not None else "")
    if c["kind"] == "VIDEO":
        fr = c["frame"]
        cap = f"Drone video {fr.time_s:.1f} s - camera facing {fr.bearing_deg:.0f} deg"
        if c.get("overview"):
            return cap + " (overview)", f"No frame faces {c['what']} at the height of the equipment; this is the clearest view of the equipment."
        off = c["off"]
        return cap, (f"Camera bearing {fr.bearing_deg:.0f} deg" + (f" is {off:.0f} deg from {c['what']}" if off is not None else f" - {c['what']}")
                     + f"; the equipment is in view ({fr.equipment:.1f} per mille of the frame).")
    s = c["still"]
    return f"{s.label} - camera facing {s.bearing_deg:.0f} deg", f"Drone still of {c['what']}: {c['why']}."


def _picture(c: dict, out: Path, caption: str) -> None:
    import cv2

    if c["kind"] == "VIDEO":
        fr = c["frame"]
        img = cv2.imread(fr.path)
        h, w = img.shape[:2]
        x0, y0, x1, y1 = fr.box
        cw = max((x1 - x0) * 1.7, 400.0, (y1 - y0) * 1.4 * 16 / 9)       # the equipment with room around it, in the video's 16:9
        ch = cw * 9 / 16
        cw, ch = min(cw, w), min(ch, h)
        left = int(min(max((x0 + x1) / 2 - cw / 2, 0), w - cw))
        top = int(min(max((y0 + y1) / 2 - ch / 2, 0), h - ch))
        img = img[top:top + int(ch), left:left + int(cw)]
    else:
        img = cv2.imread(str(c["still"].path))
    scale = 1280 / img.shape[1]
    if scale != 1:
        img = cv2.resize(img, (1280, int(img.shape[0] * scale)), interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    bar = img.copy()
    cv2.rectangle(bar, (0, img.shape[0] - 46), (img.shape[1], img.shape[0]), (20, 20, 20), -1)
    img = cv2.addWeighted(bar, 0.72, img, 0.28, 0)
    cv2.putText(img, caption, (16, img.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 88])


def attach_proofs(f: SiteFacts, discs: list[Discrepancy], redlines: list[Redline], out_dir: Path, stills: list[Still]) -> list[Proof]:
    """Write the proof pictures for every redline and return their records."""
    by_id = {d.disc_id: d for d in discs}
    proofs: list[Proof] = []
    for rl in redlines:
        d = by_id.get(rl.disc_id)
        if d is None:
            continue
        for n, c in enumerate(choose(f, d, stills), start=1):
            caption, basis = _caption(c, d)
            path = Path(out_dir) / "proof" / f"{rl.redline_id}_{n}.jpg"
            try:
                _picture(c, path, caption)
            except Exception as exc:  # noqa: BLE001 - a proof that cannot be drawn must not stop the redline
                log.warning("proof for %s not written: %s", rl.redline_id, exc, extra={"site_id": f.site_id})
                continue
            fr = c.get("frame")
            proofs.append(Proof(rl.redline_id, n, c["kind"], str(path), caption, basis, d.sector, getattr(fr, "time_s", None),
                                getattr(fr, "bearing_deg", None) if fr else c["still"].bearing_deg, c["off"]))
    return proofs


def remove_proofs(out_dir: Path) -> None:
    """Pictures of an earlier run are replaced on every run."""
    for p in (Path(out_dir) / "proof").glob("*.jpg"):
        p.unlink(missing_ok=True)
