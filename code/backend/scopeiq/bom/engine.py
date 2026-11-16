"""BOM generation: a site's extracted design plus the rulebook (bom_rules.xlsx / material_catalog.xlsx) -> BOM lines.

The engine knows how to FIND the situations the rules talk about (a new radio, a sector with new equipment, a hybrid trunk ...) and
which variables each one offers. Everything else comes from the rulebook, read at the start of the run: which items, what
quantities, the trunk length factor, the tower margin, the catalog details printed on every line. Nothing is specific to a site or
to the sample sites, and nothing is copied from an earlier run.

It never raises for a data problem. Whatever it cannot do is reported as an issue and the rest of the BOM is still produced:
  * a model that is not in the catalog -> a line marked "Review", no kit lines (the type of device is unknown), an issue
  * a rule it cannot interpret / whose child item is unknown -> not applied, an issue
  * a route length that is not documented -> trunk lines held, an issue (a length is never assumed)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from scopeiq.bom.rulebook import Rulebook
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import SECTOR_NAMES, SourceRef
from scopeiq.engine.design import Device, SiteModel
from scopeiq.reference.expressions import evaluate

log = get_logger(__name__)

DOC_LABEL = {"RFDS": "RFDS", "CD": "CD", "MA_SA": "MA/SA", "DRONE_POINTCLOUD": "Drone survey", "DRONE_VENDOR": "Drone survey",
             "DRONE": "Drone survey", "FIELD": "Drone survey"}


@dataclass
class Issue:
    severity: str                 # HIGH | MEDIUM | LOW
    code: str
    message: str
    rule_id: str = ""
    sector: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class BomLineOut:
    site_id: str
    market: str
    sector: str                   # A..D or SITE
    technology: str
    band: str
    category: str
    subcategory: str
    manufacturer: str
    model: str
    mfr_pn: str
    customer_pn: str
    description: str
    uom: str
    design_qty: float
    spare_qty: float
    supply: str
    action: str                   # Install | Remove
    source: str                   # the documents the line is based on
    drawing: str                  # the sheet / page of them
    rule_id: str
    revision: str                 # rulebook revision that produced the line
    status: str                   # Applied | Review: ...
    catalog_key: str = ""
    parent_key: str = ""
    trace: dict = field(default_factory=dict)
    unit_cost: float = 0.0
    total_cost: float = 0.0

    @property
    def total_qty(self) -> float:
        return self.design_qty + self.spare_qty


@dataclass
class BomResult:
    lines: list[BomLineOut]
    issues: list[Issue]
    trunk: dict
    revision: str
    file: str = ""                # the workbook written for this run, relative to the output folder

    def summary(self) -> dict:
        return {"lines": len(self.lines), "install_lines": sum(l.action == "Install" for l in self.lines),
                "remove_lines": sum(l.action == "Remove" for l in self.lines), "needs_review": sum(l.status != "Applied" for l in self.lines),
                "issues": len(self.issues), "revision": self.revision, "file": self.file,
                "total_cost": round(sum(l.total_cost for l in self.lines), 2)}


def _source(refs: list[SourceRef | None]) -> tuple[str, str]:
    """('RFDS R3; CD REV 1', 'A-3, A-4'): the documents and the sheets the facts behind a line were read from."""
    docs, pages = [], []
    for r in refs:
        if r is None:
            continue
        name = f"{DOC_LABEL.get(r.doc_type, r.doc_type.replace('_', ' ').title())} {r.revision}".strip()
        if name not in docs:
            docs.append(name)
        if r.page and str(r.page) not in pages:
            pages.append(str(r.page))
    return ("; ".join(docs) or "Rule only (no document)"), (", ".join(pages) or "-")


class _Builder:
    def __init__(self, m: SiteModel, rb: Rulebook):
        self.m, self.rb = m, rb
        self.lines: list[BomLineOut] = []
        self.issues: list[Issue] = []
        self._seen_issue: set = set()

    # ------------------------------------------------------------------------------------------ helpers
    def issue(self, severity: str, code: str, message: str, *, rule_id: str = "", sector: str = "", **detail) -> None:
        k = (code, rule_id, sector, message)
        if k not in self._seen_issue:
            self._seen_issue.add(k)
            self.issues.append(Issue(severity, code, message, rule_id, sector, detail))

    def _technology_band(self, item, parent_item, device: Device | None) -> tuple[str, str]:
        src = parent_item or item
        return (src.technology or ""), (src.bands or (device.bands if device else "") or "")

    def add(self, item, sector: str, qty: float, spare: float, action: str, rule_id: str, *, parent_key: str = "", device: Device | None = None,
            refs: list | None = None, trace: dict | None = None, status: str = "Applied") -> None:
        parent_item = self.rb.catalog.items.get(parent_key) if parent_key else None
        if not item.approved and status == "Applied":
            status = "Review: part is not customer-approved"
            self.issue("HIGH", "PART_NOT_APPROVED", f"{item.key} ({item.model}) is not customer-approved but {rule_id} selects it", rule_id=rule_id, sector=sector)
        tech, band = self._technology_band(item, parent_item, device)
        source, drawing = _source(refs or [])
        unit_cost = round(item.unit_cost if item and item.unit_cost is not None else 0.0, 2) if action == "Install" else 0.0
        total_cost = round(unit_cost * (qty + spare), 2)
        self.lines.append(BomLineOut(
            self.m.site_id, self.m.market, sector, tech, band, item.category, item.subcategory, item.manufacturer, item.model, item.mfr_pn,
            item.customer_pn, item.description, item.uom, qty, spare, "N/A (existing)" if action == "Remove" else item.supply, action, source, drawing,
            rule_id, self.rb.revision, status, item.key, parent_key, dict(trace or {}), unit_cost, total_cost))

    def fire(self, trigger: str, sector: str, variables: dict, *, device: Device | None = None, parent_key: str = "", refs: list | None = None,
             child_override: str | None = None, action: str = "Install", trace: dict | None = None) -> None:
        for r in self.rb.by_trigger(trigger):
            child = r.child
            if child == "(device)":
                child = device.key if device else None
            elif child.endswith("*"):
                child = child_override
            if not child:
                continue
            try:
                qty, spare = float(evaluate(r.qty_expr or "0", variables)), float(evaluate(r.spare_expr or "0", variables))
            except Exception as exc:  # noqa: BLE001 - a rule that cannot be evaluated here must not stop the others
                self.issue("MEDIUM", "RULE_ERROR", f"{r.rule_id} could not be evaluated for {sector}: {exc}", rule_id=r.rule_id, sector=sector)
                continue
            if qty <= 0 and spare <= 0:
                continue
            item = self.rb.catalog.items.get(child)
            if item is None:
                self.issue("HIGH", "CHILD_UNKNOWN", f"{r.rule_id}: '{child}' is not in the material catalog", rule_id=r.rule_id, sector=sector)
                continue
            self.add(item, sector, qty, spare, action, r.rule_id, parent_key=parent_key, device=device, refs=refs, trace=dict(trace or {}, trigger=trigger))

    def unmatched(self, d: Device, action: str) -> None:
        """A device whose model is not in the catalog: shown, flagged, and no kit lines (its type is not known)."""
        rule = "R-RMV-01" if action == "Remove" else "R-EQ-01"
        pos = f" position {d.position}" if d.position is not None else ""
        self.issue("HIGH", "MODEL_NOT_IN_CATALOG", f"'{d.model_text}' at {SECTOR_NAMES.get(d.sector, d.sector)}{pos} is not in the material catalog: "
                   f"{'its kit lines were not created' if d.kind == 'unknown' else 'it is listed for review'}", rule_id=rule, sector=d.sector, model=d.model_text)
        source, drawing = _source([d.ref])
        self.lines.append(BomLineOut(self.m.site_id, self.m.market, d.sector, "", d.bands or "", "Major Equipment" if d.kind != "unknown" else "", "", "",
                                     d.model_text, "", "", "Model not found in the material catalog", "EA", 1.0, 0.0, "", action, source, drawing, rule,
                                     self.rb.revision, "Review: model not in the material catalog", "", "", {"position": d.position, "basis": d.basis}))

    # ------------------------------------------------------------------------------------------ the engine
    def run(self) -> dict:
        m, rb = self.m, self.rb
        if m.unmatched_basebands:
            for model in m.unmatched_basebands:
                self.issue("HIGH", "MODEL_NOT_IN_CATALOG", f"Baseband '{model}' is not in the material catalog: not listed, no kit lines", rule_id="R-BB-01", sector="SITE")
        rfds_ref = next((d.ref for d in m.devices if d.basis == "RFDS" and d.ref), None)

        # the equipment itself: installs and removals
        for d in m.devices:
            if d.status == "New":
                if d.key:
                    self.fire("NEW_MAJOR", d.sector, {}, device=d, refs=[d.ref], trace={"position": d.position, "basis": d.basis})
                else:
                    self.unmatched(d, "Install")
            elif d.status == "Remove":
                if d.key:
                    self.fire("REMOVE_DEVICE", d.sector, {}, device=d, refs=[d.ref], action="Remove", trace={"position": d.position, "basis": d.basis})
                else:
                    self.unmatched(d, "Remove")
        for bb in m.basebands:
            bd = Device("SITE", None, bb, "baseband", "New", None, "RFDS", rfds_ref)
            self.fire("NEW_MAJOR", "SITE", {}, device=bd, refs=[rfds_ref], trace={"basis": "RFDS"})
            self.fire("NEW_BASEBAND", "SITE", {}, parent_key=bb, refs=[rfds_ref], trace={"basis": "RFDS"})

        # the kit for each new device
        antennas = {(d.sector, d.position): d for d in m.devices if d.kind in ("passive", "air") and d.status != "Remove"}
        for d in m.new():
            if not d.key:
                if d.kind == "unknown":                                  # already reported by `unmatched`: its type is not known, so no kit applies
                    continue
            it = rb.catalog.items.get(d.key) if d.key else None
            base = {"position": d.position}
            if d.kind == "radio":
                ports = it.rf_ports if it else 0
                if not ports:
                    self.issue("MEDIUM", "PORTS_UNKNOWN", f"RF port count of '{d.model_text or d.key}' is not in the catalog: RF jumpers for it were not counted",
                               rule_id="R-RAD-06", sector=d.sector)
                self.fire("NEW_RADIO", d.sector, {"ports": ports}, parent_key=d.key or "", device=d, refs=[d.ref], trace=base)
                fed = antennas.get((d.sector, d.position))
                if fed is None or fed.kind == "passive":
                    self.fire("NEW_RADIO_TO_PASSIVE", d.sector, {"ports": ports}, parent_key=d.key or "", device=d, refs=[d.ref], trace=base)
            elif d.kind == "air":
                self.fire("NEW_AAU", d.sector, {}, parent_key=d.key or "", device=d, refs=[d.ref], trace=base)
            elif d.kind == "passive":
                self.fire("NEW_PASSIVE", d.sector, {}, parent_key=d.key or "", device=d, refs=[d.ref], trace=base)

        # mounting, per sector with new equipment
        for sec in sorted({d.sector for d in m.new()}):
            sec_ref = m.refs.get(("frame", sec))
            self.fire("SECTOR_NEW_DEVICE", sec, {}, refs=[next((d.ref for d in m.new() if d.sector == sec and d.ref), None)])
            if sec in m.new_frames:
                self.fire("SECTOR_NEW_FRAME", sec, {}, refs=[sec_ref], trace={"basis": "CD"})
                continue
            if m.rooftop and not m.sleds.get(sec, False):
                basis = m.sled_basis.get(sec, "CD")
                self.fire("ROOF_SECTOR_NO_SLED", sec, {}, refs=[m.refs.get(("sled", sec)) or sec_ref], trace={"basis": basis})
                continue
            for pos in sorted({d.position for d in m.new("air", "passive") if d.sector == sec and d.position is not None}):
                if (sec, pos) not in m.pipes:
                    self.fire("POSITION_NO_PIPE", sec, {}, refs=[m.refs.get(("pipe", sec, pos)) or sec_ref],
                              trace={"basis": m.pipe_basis.get(sec, "CD"), "position": pos})
        for mod in m.ma_mods:
            rules = rb.by_trigger("MA_REINFORCEMENT")
            if mod.get("kit_key") and rules and all(mod["kit_key"] != r.child for r in rules):
                self.issue("MEDIUM", "MA_KIT_DIFFERS", f"The MA report asks for kit '{mod['kit_key']}' for {mod.get('sector', 'the site')}; the rules supply "
                           f"'{rules[0].child}'. Please review.", rule_id=rules[0].rule_id, sector=str(mod.get("sector") or "SITE"))
            self.fire("MA_REINFORCEMENT", str(mod.get("sector") or "SITE"), {"ma_qty": mod.get("qty", 0)}, refs=[m.refs.get("ma")], trace={"basis": "MA"})

        tp = self.trunks()

        # DC power, then the per-site items
        added = removed = 0.0
        for d in m.new() + m.removed():
            it = rb.catalog.items.get(d.key) if d.key else None
            if it is None:
                if d.kind != "unknown" or d.status == "New":
                    self.issue("MEDIUM", "POWER_UNKNOWN", f"DC load of '{d.model_text}' is unknown (not in the catalog): the rectifier count may be understated",
                               rule_id="R-PWR-01", sector=d.sector)
                continue
            if d.status == "New":
                added += it.power_w
            else:
                removed += it.power_w
        self.fire("NET_DC_LOAD", "SITE", {"added_w": added, "removed_w": removed}, refs=[rfds_ref], trace={"added_w": added, "removed_w": removed})
        self.fire("PER_SITE", "SITE", {})
        return tp

    def trunks(self) -> dict:
        m, rb = self.m, self.rb
        powered = m.new("radio", "air")
        tp = {"count": 0, "powered_new": len(powered), "vertical_ft": None, "horizontal_ft": m.horizontal_ft, "horizontal_basis": m.horizontal_basis,
              "required_ft": None, "length_ft": None, "key": None, "held": False, "reason": ""}
        if not powered:
            return tp
        rules = rb.by_trigger("TRUNK")
        if not rules:
            tp.update(held=True, reason="No applied rule creates hybrid trunks")
            self.issue("HIGH", "TRUNK_HELD", tp["reason"] + ": trunk lines were not created")
            return tp
        try:
            tp["count"] = int(evaluate(rules[0].qty_expr or "0", {"powered_new": len(powered)}))
        except Exception as exc:  # noqa: BLE001
            tp.update(held=True, reason=f"{rules[0].rule_id} could not be evaluated: {exc}")
            self.issue("HIGH", "TRUNK_HELD", tp["reason"], rule_id=rules[0].rule_id)
            return tp
        if m.rooftop:
            vertical = m.vertical_ft                                   # riser run on the CD
        else:
            rcs = [d.rad_center_ft for d in powered if d.rad_center_ft is not None]
            vertical = (max(rcs) + rb.tower_margin_ft) if rcs and rb.tower_margin_ft is not None else None
        tp["vertical_ft"] = vertical
        reason = ""
        if rb.length_factor is None or not rb.trunk_steps:
            reason = "The trunk length factor or the list of trunk lengths is missing from the rules files"
        elif vertical is None or m.horizontal_ft is None:
            reason = "Route length not documented (CBL-01): the vertical or horizontal run is not on the CD or in the drone survey"
        if reason:
            tp.update(held=True, reason=reason)
            self.issue("HIGH", "TRUNK_HELD", reason + ": trunk lines were held, never assumed", rule_id=rules[0].rule_id)
            return tp
        req = round(rb.length_factor * (vertical + m.horizontal_ft), 1)
        step = next(((ft, key) for ft, key in rb.trunk_steps if ft >= req and key in rb.catalog), None)
        if step is None:
            tp.update(required_ft=req, held=True, reason=f"Required length {req} ft exceeds the longest trunk in the catalog")
            self.issue("HIGH", "TRUNK_HELD", tp["reason"] + ": engineering review", rule_id=rules[0].rule_id)
            return tp
        tp.update(required_ft=req, length_ft=step[0], key=step[1])
        refs = [m.refs.get("trunk")]
        v = {"powered_new": len(powered), "trunk_length_ft": step[0]}
        self.fire("TRUNK", "SITE", v, child_override=step[1], refs=refs, trace={"basis": m.horizontal_basis, "required_ft": req})
        for _ in range(tp["count"]):
            self.fire("PER_TRUNK", "SITE", v, refs=refs)
        ovp = sum(l.design_qty for l in self.lines if l.subcategory == "Surge Protection" and l.trace.get("trigger") == "PER_TRUNK")
        for _ in range(int(round(ovp))):                              # the OVP boxes the trunk rules just listed, counted from the catalog
            self.fire("PER_OVP", "SITE", v, refs=refs)
        return tp


def _consolidate(lines: list[BomLineOut]) -> list[BomLineOut]:
    """Sum identical lines (same sector, part, rule, parent, action) - one line per kit per sector."""
    out: dict[tuple, BomLineOut] = {}
    for l in lines:
        k = (l.sector, l.catalog_key or l.model, l.rule_id, l.parent_key, l.action)
        if k in out:
            first = out[k]
            first.design_qty += l.design_qty
            first.spare_qty += l.spare_qty
            first.trace["instances"] = first.trace.get("instances", 1) + 1
            if l.source not in first.source.split("; "):
                first.source = "; ".join([s for s in (first.source.split("; ") + l.source.split("; ")) if s and s != "Rule only (no document)"]) or first.source
            pages = [p for p in (first.drawing.split(", ") + l.drawing.split(", ")) if p and p != "-"]
            first.drawing = ", ".join(dict.fromkeys(pages)) or "-"
        else:
            out[k] = l
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "SITE": 9}
    return sorted(out.values(), key=lambda l: (order.get(l.sector, 5), l.action != "Install", l.rule_id, l.catalog_key or l.model))


@log_call()
def generate(model: SiteModel, rb: Rulebook) -> BomResult:
    """The BOM for one site. Always returns a result; whatever could not be done is in `issues`."""
    b = _Builder(model, rb)
    b.issues.extend(Issue(i["severity"], i["code"], i["message"], i.get("rule_id", "")) for i in rb.issues)
    try:
        trunk = b.run()
    except Exception as exc:  # noqa: BLE001 - a bug or an unexpected shape of data must not lose the lines already built
        log.exception("BOM engine failed for %s", model.site_id)
        b.issue("HIGH", "ENGINE_ERROR", f"The BOM could not be completed: {type(exc).__name__}: {exc}")
        trunk = {"count": 0, "held": True, "reason": "engine error"}
    return BomResult(_consolidate(b.lines), b.issues, trunk, rb.revision)
