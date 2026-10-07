"""Pipeline step 4 - Delta: the site's target configuration and what changes to reach it.

Two views of the same site are built with the same structure so the same rules can run on both:
  * AS_DRAWN - the CD exactly as drawn (devices, positions, pipes, sleds, frames, cable schedule).
               Kitting rules on this view reproduce what the Ericsson tool should have produced for REV 0,
               so REV 0 differences against it are tool errors.
  * FINAL    - the corrected site: RFDS governs RF (models, positions, rad centers), the field survey governs
               existing physical conditions (pipes, sleds, route length, unrecorded equipment to remove) and
               the MA governs mount modifications. Kitting rules on this view produce the REV 1 BOM.
Differences between the two views are caused by discrepancies, and every line keeps that link.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from scopeiq.common.logging import get_logger, log_call
from scopeiq.config import get_settings
from scopeiq.domain import DeltaLine, SiteFacts, SourceRef
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)

AS_DRAWN, FINAL = "AS_DRAWN", "FINAL"


@dataclass
class Device:
    sector: str
    position: int | None
    key: str
    kind: str
    status: str               # New | Existing | Remove
    rad_center_ft: float | None
    basis: str                # RFDS | CD | FIELD
    ref: SourceRef | None = None
    from_position: int | None = None


@dataclass
class SiteModel:
    mode: str
    site_id: str
    rooftop: bool
    rfds_rev: str
    devices: list[Device] = field(default_factory=list)
    pipes: set = field(default_factory=set)               # {(sector, position)} existing pipes
    pipe_basis: dict = field(default_factory=dict)        # sector -> FIELD | CD
    sleds: dict = field(default_factory=dict)             # sector -> bool (existing sled)
    sled_basis: dict = field(default_factory=dict)
    new_frames: set = field(default_factory=set)
    ma_mods: list[dict] = field(default_factory=list)
    basebands: list[str] = field(default_factory=list)
    vertical_ft: float | None = None
    horizontal_ft: float | None = None
    horizontal_basis: str = ""
    notes: list[str] = field(default_factory=list)

    def new(self, *kinds: str) -> list[Device]:
        return [d for d in self.devices if d.status == "New" and (not kinds or d.kind in kinds)]

    def removed(self) -> list[Device]:
        return [d for d in self.devices if d.status == "Remove"]


def _baseband_keys(facts: SiteFacts, ref: ReferenceData) -> list[str]:
    out = []
    for b in facts.basebands:
        if str(b.get("action", "New")).lower().startswith("new"):
            cat, _ = ref.catalog.resolve(b.get("model", ""), kinds=("baseband",))
            if cat:
                out += [cat.key] * int(b.get("qty", 1) or 1)
    return out


@log_call()
def build_model(facts: SiteFacts, ref: ReferenceData, mode: str, discrepancies=None) -> SiteModel:
    st = get_settings()
    m = SiteModel(mode, facts.site_id, facts.is_rooftop, facts.rfds_revision or "")
    cd_dev = [i for i in facts.cd_items if i.is_device and i.catalog_key]
    cd_pipes = {(i.sector, i.position) for i in facts.cd_items if i.kind == "pipe" and i.status == "Existing"}
    cd_sleds = {k: v.sled.get("CD") for k, v in facts.sectors.items() if "CD" in v.sled}
    m.new_frames = {k for k, v in facts.sectors.items() if v.new_frame}
    m.basebands = _baseband_keys(facts, ref)
    cdt, ft = facts.trunks.get("CD"), facts.trunks.get("FIELD")

    if mode == AS_DRAWN:
        for i in cd_dev:
            m.devices.append(Device(i.sector, i.position, i.catalog_key, i.kind, "Remove" if i.status == "Remove" else i.status,
                                    i.rad_center_ft, "CD", i.ref))
        m.pipes, m.sleds = cd_pipes, dict(cd_sleds)
        m.pipe_basis = {s: "CD" for s, _ in cd_pipes}
        m.sled_basis = {s: "CD" for s in cd_sleds}
        m.horizontal_ft, m.horizontal_basis = (cdt.horizontal_ft, "CD") if cdt else (None, "")
        if m.rooftop:
            m.vertical_ft = cdt.vertical_ft if cdt else None
        else:
            rcs = [d.rad_center_ft for d in m.new("radio", "air") if d.rad_center_ft is not None]
            m.vertical_ft = (max(rcs) + 5) if rcs else (cdt.vertical_ft if cdt else None)
        return m

    # FINAL ------------------------------------------------------------------------------------------
    existing_by_key: dict[tuple, list] = {}
    for i in facts.rfds_existing:
        if i.is_device and i.catalog_key:
            existing_by_key.setdefault((i.sector, i.catalog_key), []).append(i.position)
    for i in facts.rfds_final:
        if not i.is_device or not i.catalog_key:
            continue
        status = "New" if i.status == "New" else "Remove" if i.status == "Remove" else "Existing"
        frm = None
        if status == "Existing":
            prev = existing_by_key.get((i.sector, i.catalog_key), [])
            if prev and i.position not in prev:
                frm = prev[0]
        m.devices.append(Device(i.sector, i.position, i.catalog_key, i.kind, status, i.rad_center_ft, "RFDS", i.ref, frm))
    # implicit removals: on RFDS existing but not on final (v2 / PDF layouts list removals implicitly)
    final_keys = {(d.sector, d.position, d.key) for d in m.devices}
    final_count: dict[tuple, int] = {}
    for d in m.devices:
        final_count[(d.sector, d.key)] = final_count.get((d.sector, d.key), 0) + (d.status != "Remove")
    for i in facts.rfds_existing:
        if not i.is_device or not i.catalog_key:
            continue
        k = (i.sector, i.catalog_key)
        if final_count.get(k, 0) > 0:
            final_count[k] -= 1
            continue
        if (i.sector, i.position, i.catalog_key) not in {(d.sector, d.position, d.key) for d in m.devices if d.status == "Remove"}:
            m.devices.append(Device(i.sector, i.position, i.catalog_key, i.kind, "Remove", i.rad_center_ft, "RFDS", i.ref))
    # unrecorded field equipment (FLD-01): not in the final design -> removal line
    for dsc in discrepancies or []:
        if dsc.rule_id == "FLD-01" and dsc.found:
            kind = ref.catalog.get(dsc.found).kind if dsc.found in ref.catalog else "radio"
            m.devices.append(Device(dsc.sector, dsc.position, dsc.found, kind, "Remove", None, "FIELD"))
            m.notes.append(f"{dsc.found} at {dsc.sector}{dsc.position}: removal added from drone survey ({dsc.disc_id})")
    # mounts: field governs where the drone covered the sector, otherwise the CD
    field_secs = {i.sector for i in facts.field_items}
    field_pipes = {(i.sector, i.position) for i in facts.field_items if i.kind == "pipe"}
    for sec in {d.sector for d in m.devices} | set(cd_sleds):
        if sec in field_secs or (m.rooftop and facts.sectors.get(sec) and "FIELD" in facts.sectors[sec].sled):
            m.pipes |= {p for p in field_pipes if p[0] == sec}
            m.pipe_basis[sec] = "FIELD"
        else:
            m.pipes |= {p for p in cd_pipes if p[0] == sec}
            m.pipe_basis[sec] = "CD"
        si = facts.sectors.get(sec)
        if si and "FIELD" in si.sled:
            m.sleds[sec], m.sled_basis[sec] = si.sled["FIELD"], "FIELD"
        elif sec in cd_sleds:
            m.sleds[sec], m.sled_basis[sec] = cd_sleds[sec], "CD"
    if facts.ma:
        m.ma_mods = [x for x in facts.ma.modifications if x.get("kit_key")]
    # cable route: measured wins when it differs beyond tolerance (FLD-06), else the CD value stands
    tol = float(st.get("engine.route_tolerance_ft", 10))
    if cdt and cdt.horizontal_ft is not None and ft and ft.horizontal_ft is not None:
        if abs(cdt.horizontal_ft - ft.horizontal_ft) > tol:
            m.horizontal_ft, m.horizontal_basis = round(ft.horizontal_ft), "FIELD"
        else:
            m.horizontal_ft, m.horizontal_basis = cdt.horizontal_ft, "CD"
    elif cdt and cdt.horizontal_ft is not None:
        m.horizontal_ft, m.horizontal_basis = cdt.horizontal_ft, "CD"
    elif ft and ft.horizontal_ft is not None:
        m.horizontal_ft, m.horizontal_basis = round(ft.horizontal_ft), "FIELD"
    if m.rooftop:
        m.vertical_ft = cdt.vertical_ft if cdt else None          # riser run from the CD
    else:
        rcs = [d.rad_center_ft for d in m.new("radio", "air") if d.rad_center_ft is not None]
        m.vertical_ft = (max(rcs) + 5) if rcs else None
    return m


@log_call()
def compute_delta(final: SiteModel) -> list[DeltaLine]:
    """Equipment delta (guide 6.3): NEW / EXISTING / REMOVED / RELOCATED / REUSED per device."""
    out = []
    for d in final.devices:
        if d.status == "New":
            action = "NEW"
        elif d.status == "Remove":
            action = "REMOVED"
        elif d.from_position is not None:
            action = "REUSED" if d.kind == "radio" else "RELOCATED"
        else:
            action = "EXISTING"
        out.append(DeltaLine(final.site_id, d.sector, d.position, d.kind, d.key, action, d.from_position, d.rad_center_ft,
                             {"RFDS": f"RFDS {final.rfds_rev} final configuration", "FIELD": "Drone survey (unrecorded equipment)",
                              "CD": "CD"}[d.basis], d.ref))
    for key in final.basebands:
        out.append(DeltaLine(final.site_id, "SITE", None, "baseband", key, "NEW", basis=f"RFDS {final.rfds_rev} Baseband & Power"))
    return out
