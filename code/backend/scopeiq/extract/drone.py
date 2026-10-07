"""Drone survey extraction: what is ACTUALLY on the structure (guide 6.2, field verification).

Sources, in order of preference:
  1. Vendor measurement CSV (survey vendor's object list)               method VENDOR_CSV
  2. LiDAR point cloud (LAS/LAZ, ASPRS classes 64-68)                  method POINTCLOUD
     - antennas / radios: voxel connected components of class 64 / 65
     - mount pipes: vertical columns of class 66 (>= 1.5 m z-span in a 10 cm xy cell)
     - roof sleds: class 66 lying on the roof slab (rooftop sites)
     - cable route: horizontal class 67 run from the tower base to the cabinet (class 68)
  3. Orbit video frames (see extract/video.py) - visual evidence only, never a measurement.

Both measurement paths produce FieldObjects; `assemble_field_items` then turns them into FIELD ConfigItems
(sector, position, catalog model from dimensions, rad center) and a FIELD TrunkInfo with the measured route.
Models are inferred from object dimensions against the catalog, so field equipment carries a confidence and
anything uncertain is marked for human review instead of being trusted.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from scopeiq.common.errors import ExtractionError
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import ConfigItem, ExtractedField, FieldObject, SectorInfo, SourceRef, TrunkInfo, sector_code
from scopeiq.reference.catalog import Catalog

log = get_logger(__name__)

FT = 0.3048
IN = 0.0254
CLS_ANT, CLS_RRU, CLS_MOUNT, CLS_CABLE, CLS_CAB, CLS_BUILDING = 64, 65, 66, 67, 68, 6


def load_metadata(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Drone metadata {Path(path).name} unreadable: {exc}", cause=exc) from exc


def _f(v) -> float | None:
    try:
        return float(v) if str(v).strip() != "" else None
    except ValueError:
        return None


def _wrap(a: float) -> float:
    return (a + 180) % 360 - 180


def _bearing(x: float, y: float) -> float:
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ---------------------------------------------------------------- vendor CSV
@log_call()
def read_vendor_csv(path: Path) -> list[FieldObject]:
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            typ = r["object_type"]
            if typ.startswith("Cable route"):
                typ = "Cable route"
            b = _f(r.get("bearing_from_structure_deg"))
            fa = _f(r.get("facing_azimuth_deg"))
            dims = tuple(_f(r.get(k)) for k in ("height_in", "width_in", "depth_in"))
            out.append(FieldObject(r["object_id"], typ, sector_code(r["sector_inferred"]) if r.get("sector_inferred") else None,
                                   b % 360 if b is not None else None, fa % 360 if fa is not None else None, _f(r.get("center_height_ft")),
                                   dims if all(d is not None for d in dims) else None, r.get("model_guess", "") or "",
                                   _f(r.get("confidence")) or 0.0, _f(r.get("route_length_ft")), "VENDOR_CSV"))
    return out


# ---------------------------------------------------------------- point cloud
def _components(pts: np.ndarray, voxel: float, min_pts: int = 30) -> list[np.ndarray]:
    """Connected components of occupied voxels (26-neighbourhood) -> list of point-index arrays."""
    if len(pts) == 0:
        return []
    keys = np.floor(pts / voxel).astype(np.int64)
    vox: dict[tuple, list[int]] = defaultdict(list)
    for i, k in enumerate(map(tuple, keys)):
        vox[k].append(i)
    seen: set = set()
    comps = []
    offs = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)]
    for start in vox:
        if start in seen:
            continue
        stack, members = [start], []
        seen.add(start)
        while stack:
            k = stack.pop()
            members.extend(vox[k])
            for o in offs:
                n = (k[0] + o[0], k[1] + o[1], k[2] + o[2])
                if n in vox and n not in seen:
                    seen.add(n)
                    stack.append(n)
        if len(members) >= min_pts:
            comps.append(np.array(members))
    return comps


def _box(p: np.ndarray) -> tuple[np.ndarray, tuple[float, float, float], float]:
    """Centre, (height, width, depth) in metres and the horizontal minor-axis bearing of a box-shaped cluster."""
    xy = p[:, :2] - p[:, :2].mean(axis=0)
    w, v = np.linalg.eigh(np.cov(xy.T)) if len(p) > 3 else (np.array([1, 1]), np.eye(2))
    major, minor = v[:, 1], v[:, 0]
    pa, pb = xy @ major, xy @ minor
    centre = np.array([(p[:, 0].min() + p[:, 0].max()) / 2, (p[:, 1].min() + p[:, 1].max()) / 2, (p[:, 2].min() + p[:, 2].max()) / 2])
    centre[:2] = p[:, :2].mean(axis=0) + major * (pa.max() + pa.min()) / 2 + minor * (pb.max() + pb.min()) / 2
    dims = (float(np.ptp(p[:, 2])), float(np.ptp(pa)), float(np.ptp(pb)))
    return centre, dims, _bearing(minor[0], minor[1])


def _split_side_by_side(p: np.ndarray, max_width_m: float) -> list[np.ndarray]:
    """Devices mounted side by side touch in the cloud: split a cluster wider than one device at the widest
    gap (or the middle) along its major horizontal axis, recursively."""
    if len(p) < 60:
        return [p]
    xy = p[:, :2] - p[:, :2].mean(axis=0)
    _, v = np.linalg.eigh(np.cov(xy.T))
    t = xy @ v[:, 1]
    if np.ptp(t) <= max_width_m * 1.45:
        return [p]
    ts = np.sort(t)
    gaps = np.diff(ts)
    lo, hi = int(len(ts) * 0.25), int(len(ts) * 0.75)
    cut = ts[lo + int(np.argmax(gaps[lo:hi]))] if hi > lo else float(np.median(t))
    return _split_side_by_side(p[t <= cut], max_width_m) + _split_side_by_side(p[t > cut], max_width_m)


@log_call()
def read_pointcloud(path: Path, *, rooftop: bool, max_width_m: dict[str, float] | None = None) -> tuple[list[FieldObject], dict]:
    """max_width_m: widest single device per class {"Antenna": m, "Remote radio": m} (from the catalog);
    wider clusters are split."""
    max_width_m = {"Antenna": 0.5, "Remote radio": 0.34, **(max_width_m or {})}
    import laspy

    try:
        las = laspy.read(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Point cloud {Path(path).name} unreadable: {exc}", cause=exc) from exc
    xyz = np.c_[las.x, las.y, las.z].astype(float)
    cls = np.asarray(las.classification)
    stats = {"points": int(len(xyz)), "classes": {int(c): int(n) for c, n in zip(*np.unique(cls, return_counts=True))}}
    roof_z = float(np.percentile(xyz[cls == CLS_BUILDING][:, 2], 99)) if rooftop and (cls == CLS_BUILDING).any() else 0.0
    stats["roof_z_m"] = round(roof_z, 2)
    objs: list[FieldObject] = []

    def add(typ, centre, dims_m, facing=None, conf=0.9, route=None):
        oid = f"PC-{len(objs) + 1:03d}"
        dims = tuple(round(d / IN, 1) for d in dims_m) if dims_m else None
        objs.append(FieldObject(oid, typ, None, round(_bearing(centre[0], centre[1]), 1) if centre is not None else None,
                                round(facing, 1) if facing is not None else None,
                                round(centre[2] / FT, 1) if centre is not None else None, dims, "", conf, route, "POINTCLOUD"))

    for c_id, typ in ((CLS_ANT, "Antenna"), (CLS_RRU, "Remote radio")):
        pts = xyz[cls == c_id]
        clusters = [pts[c] for c in _components(pts, 0.08 if c_id == CLS_ANT else 0.05)]
        clusters = [part for c in clusters for part in _split_side_by_side(c, max_width_m[typ])]
        for p in clusters:
            centre, dims, minor_b = _box(p)
            outward = _bearing(centre[0], centre[1])
            facing = minor_b if abs(_wrap(minor_b - outward)) <= 90 else (minor_b + 180) % 360
            add(typ, centre, dims, facing if typ == "Antenna" else None, conf=min(0.97, 0.6 + len(p) / 3000))

    # mount pipes: vertical columns in class 66
    m = xyz[cls == CLS_MOUNT]
    if len(m):
        cells: dict[tuple, list[int]] = defaultdict(list)
        for i, k in enumerate(map(tuple, np.floor(m[:, :2] / 0.1).astype(np.int64))):
            cells[k].append(i)
        col_idx = []
        for k, idx in cells.items():
            z = m[idx, 2]
            if np.ptp(z) >= 1.5:
                col_idx.extend(idx)
        cols = m[col_idx]
        for comp in _components(cols * [1, 1, 0.05], 0.12, min_pts=20):     # squash z so a column is one component
            p = cols[comp]
            z0, z1 = p[:, 2].min(), p[:, 2].max()
            centre = np.array([p[:, 0].mean(), p[:, 1].mean(), (z0 + z1) / 2])
            add("Mount pipe", centre, (z1 - z0, 0.073, 0.073), conf=0.9)
        if rooftop:
            low = m[m[:, 2] < roof_z + 0.5]
            for comp in _components(low, 0.15, min_pts=100):
                centre, dims, _ = _box(low[comp])
                if dims[1] > 2.0:
                    add("Roof sled", centre, dims, conf=0.92)
    # cable route (tower sites): horizontal cable run from the tower base to the cabinet
    cab = xyz[cls == CLS_CAB]
    cab_c = cab.mean(axis=0) if len(cab) else None
    if cab_c is not None:
        stats["cabinet_bearing_deg"] = round(_bearing(cab_c[0], cab_c[1]), 1)
    if not rooftop and cab_c is not None:
        cable = xyz[cls == CLS_CABLE]
        horiz = cable[(cable[:, 2] > 2.0) & (cable[:, 2] < 3.2)]
        if len(horiz):
            d = np.hypot(horiz[:, 0], horiz[:, 1])
            start = horiz[np.argmin(d)]
            length_m = float(np.max(np.hypot(horiz[:, 0] - start[0], horiz[:, 1] - start[1])))
            add("Cable route", None, None, conf=0.88, route=round(length_m / FT, 1))
    else:
        stats["route_note"] = "Rooftop: the cabinet-to-sled cable path is not visible in the point cloud; route length comes from the CD"
    log.info("point cloud: %d objects", len(objs), extra={"stats": stats})
    return objs, stats


# ---------------------------------------------------------------- assembly
def _circ_mean(angles: list[float]) -> float:
    s = sum(math.sin(math.radians(a)) for a in angles)
    c = sum(math.cos(math.radians(a)) for a in angles)
    return (math.degrees(math.atan2(s, c)) + 360) % 360


def _dims_error(obj: FieldObject, it) -> float:
    if not obj.dims_in or not it.height_m:
        return 9e9
    h, w, d = (x * IN for x in obj.dims_in)
    return abs(h - it.height_m) / it.height_m + abs(w - it.width_m) / it.width_m + 0.5 * abs(d - it.depth_m) / max(it.depth_m, 0.05)


DESIGN_MATCH_MAX_ERR = 0.35     # dims error under which a field object is accepted as the expected design item


def _match_model(obj: FieldObject, catalog: Catalog, kinds: tuple[str, ...], prefer: set[str] | None = None) -> tuple[str | None, float, list[str]]:
    """Identify a model from the vendor's guess or from dimensions. Returns (key, confidence, look-alikes).
    Models whose dimensions are indistinguishable (within 0.05 error) are look-alikes; among them a model already
    present on the site is preferred and confidence is halved so a person confirms it."""
    if obj.model_guess:
        cat, score = catalog.resolve(obj.model_guess, kinds=kinds)
        if cat and score >= 0.9:
            return cat.key, round(min(obj.confidence, 0.99) * score, 3), []
    if not obj.dims_in:
        return None, 0.0, []
    scored = sorted((_dims_error(obj, catalog.get(k)), k) for kind in kinds for k in catalog.keys_of_kind(kind))
    if not scored or scored[0][0] > 5:
        return None, 0.0, []
    best_err = scored[0][0]
    alike = [k for e, k in scored if e <= best_err + 0.05]
    pick = next((k for k in alike if prefer and k in prefer), alike[0])
    score = max(0.0, 1 - _dims_error(obj, catalog.get(pick)) / 1.5) * (0.5 if len(alike) > 1 else 1.0)
    return pick, round(min(obj.confidence, 0.99) * score, 3), [k for k in alike if k != pick]


@log_call()
def assemble_field_items(objs: list[FieldObject], *, site_id: str, doc_id: str, method: str, catalog: Catalog,
                         design_azimuths: dict[str, float], rooftop: bool,
                         expected: list[ConfigItem] | None = None) -> tuple[list[ConfigItem], dict[str, SectorInfo], TrunkInfo | None, list[ExtractedField]]:
    """FieldObjects -> FIELD ConfigItems. `design_azimuths` (sector -> az from RFDS/CD) is used only to name sectors.

    `expected` = devices the design documents say are on the structure today (RFDS existing + CD existing/remove).
    Field objects at a position are first paired with the expected devices there when their measured dimensions
    fit (vision confirms, it does not re-identify); objects left over are identified from the catalog by
    dimensions alone and show up in reconciliation as unrecorded equipment.
    """
    ref = lambda o: SourceRef(doc_id, "DRONE", "", "", f"{method} {o.object_id}")  # noqa: E731

    def nearest_sector(bearing: float | None) -> str | None:
        if bearing is None or not design_azimuths:
            return None
        sec, az = min(design_azimuths.items(), key=lambda kv: abs(_wrap(bearing - kv[1])))
        return sec if abs(_wrap(bearing - az)) <= 60 else None

    eq = [o for o in objs if o.object_type in ("Antenna", "Remote radio", "Mount pipe", "Roof sled")]
    for o in eq:
        o.sector = o.sector or nearest_sector(o.facing_az_deg if o.facing_az_deg is not None else o.bearing_deg)
    sectors: dict[str, SectorInfo] = {}
    # field azimuth per sector = circular mean of the antennas' facing azimuth (sled / pipe bearing as fallback)
    for sec in sorted({o.sector for o in eq if o.sector}):
        facings = [o.facing_az_deg for o in eq if o.sector == sec and o.object_type == "Antenna" and o.facing_az_deg is not None]
        si = sectors.setdefault(sec, SectorInfo(sec))
        if facings:
            si.azimuth["FIELD"] = round(_circ_mean(facings), 1)
        if rooftop:
            si.sled["FIELD"] = any(o.sector == sec and o.object_type == "Roof sled" for o in eq)
    for sec in design_azimuths:
        if rooftop:
            sectors.setdefault(sec, SectorInfo(sec)).sled.setdefault("FIELD", False)

    def centre_bearing(sec: str) -> float | None:
        si = sectors.get(sec)
        if si and "FIELD" in si.azimuth:
            return si.azimuth["FIELD"]
        sled = [o.bearing_deg for o in eq if o.sector == sec and o.object_type == "Roof sled" and o.bearing_deg is not None]
        return sled[0] if sled else design_azimuths.get(sec)

    # pipe spacing (degrees of bearing between adjacent positions), estimated from the data itself
    rel: list[float] = []
    for o in eq:
        if o.object_type == "Mount pipe" and o.sector and o.bearing_deg is not None and centre_bearing(o.sector) is not None:
            rel.append(abs(_wrap(o.bearing_deg - centre_bearing(o.sector))))
    noise = 2.5
    off = sorted(r for r in rel if r > noise)
    spacing = off[len(off) // 2] if off else None

    def pos_of(o: FieldObject) -> int | None:
        cb = centre_bearing(o.sector) if o.sector else None
        if cb is None or o.bearing_deg is None:
            return None
        r = _wrap(o.bearing_deg - cb)
        if spacing is None:
            return 2
        return 2 + max(-1, min(1, round(r / spacing)))

    items: list[ConfigItem] = []
    fields: list[ExtractedField] = []
    pipes: dict[tuple[str, int], FieldObject] = {}
    for o in eq:
        if o.object_type == "Mount pipe" and o.sector:
            p = pos_of(o)
            o.position = p
            pipes[(o.sector, p)] = o
            items.append(ConfigItem(site_id, "FIELD", o.sector, p, "pipe", "PIPE", "Mount pipe", "Existing",
                                    rad_center_ft=o.center_height_ft, ref=ref(o), confidence=o.confidence, attrs={"object_id": o.object_id}))
        elif o.object_type == "Roof sled" and o.sector:
            items.append(ConfigItem(site_id, "FIELD", o.sector, None, "sled", "SLED", "Roof sled", "Existing",
                                    ref=ref(o), confidence=o.confidence, attrs={"object_id": o.object_id}))

    def nearest_pipe_pos(o: FieldObject) -> int | None:
        cands = [(abs(_wrap(o.bearing_deg - p.bearing_deg)), pos) for (sec, pos), p in pipes.items()
                 if sec == o.sector and p.bearing_deg is not None and o.bearing_deg is not None]
        if cands and spacing and min(cands)[0] <= spacing / 2:
            return min(cands)[1]
        return pos_of(o)

    devs = [o for o in eq if o.object_type in ("Antenna", "Remote radio") and o.sector]
    for o in devs:
        o.position = nearest_pipe_pos(o)
    # pair with expected design devices per (sector, position, class) - greedy on dimension error
    paired: dict[str, tuple[str, float]] = {}
    exp_pool = defaultdict(list)
    for e in expected or []:
        if e.is_device and e.catalog_key:
            exp_pool[(e.sector, e.position, "Remote radio" if e.kind == "radio" else "Antenna")].append(e.catalog_key)
    for (sec, pos, typ), keys in exp_pool.items():
        objs_here = [o for o in devs if o.sector == sec and o.position == pos and o.object_type == typ]
        pairs = sorted(((_dims_error(o, catalog.get(k)), i, j) for i, o in enumerate(objs_here) for j, k in enumerate(keys)))
        used_o, used_k = set(), set()
        for err, i, j in pairs:
            if i in used_o or j in used_k or err > DESIGN_MATCH_MAX_ERR:
                continue
            used_o.add(i); used_k.add(j)
            paired[objs_here[i].object_id] = (keys[j], round(min(objs_here[i].confidence, 0.99) * (1 - err / 2), 3))
    ant_rc: dict[tuple[str, int], float] = {}
    for o in sorted(devs, key=lambda o: o.object_type != "Antenna"):
        kinds = ("passive", "air") if o.object_type == "Antenna" else ("radio",)
        alike: list[str] = []
        if o.object_id in paired:
            key, conf = paired[o.object_id]
        else:
            key, conf, alike = _match_model(o, catalog, kinds, prefer={e.catalog_key for e in expected or [] if e.catalog_key})
        kind = catalog.get(key).kind if key else kinds[0]
        rc = o.center_height_ft
        if o.object_type == "Antenna":
            ant_rc[(o.sector, o.position)] = rc
        else:
            rc = ant_rc.get((o.sector, o.position), pipes.get((o.sector, o.position)).center_height_ft
                            if (o.sector, o.position) in pipes else None)
        it = ConfigItem(site_id, "FIELD", o.sector, o.position, kind, key, catalog.get(key).model if key else (o.model_guess or o.object_type),
                        "Existing", rad_center_ft=rc, azimuth_deg=o.facing_az_deg, ref=ref(o), confidence=conf,
                        feeds_position=o.position if kind == "radio" else None,
                        attrs={"object_id": o.object_id, "dims_in": o.dims_in, "model_guess": o.model_guess, "method": method,
                               "matched_design": o.object_id in paired, "look_alikes": alike})
        items.append(it)
        fields.append(ExtractedField(doc_id, site_id, o.object_id, f"FIELD:{o.sector}{o.position}:{kind}", it.model_text, conf, method,
                                     needs_review=conf < 0.8))
    route = next((o for o in objs if o.object_type == "Cable route" and o.route_length_ft), None)
    trunk = TrunkInfo("FIELD", None, None, route.route_length_ft, None, None, ref(route)) if route else None
    if route:
        fields.append(ExtractedField(doc_id, site_id, route.object_id, "FIELD:route_length_ft", route.route_length_ft, route.confidence, method))
    log.info("field model (%s): %d items, spacing=%s deg, sectors=%s", method, len(items), spacing,
             {k: v.azimuth.get("FIELD") for k, v in sectors.items()}, extra={"site_id": site_id})
    return items, sectors, trunk, fields
