"""Pipeline step 5 - Generate: kitting rules (KIT_RULE table) applied to a SiteModel -> BOM lines.

Rules are data. Each rule has a TRIGGER_CODE; this module only knows how to find trigger instances
(a new radio, a sector with a new device, a trunk ...) and the variables an instance exposes. Quantities,
spares, child parts and source references come from the rule rows, so adding or changing a kit is a
reference-data change. Every line carries its RULE_ID and the source document reference (traceability).
"""
from __future__ import annotations

import math
from collections import defaultdict

from scopeiq.common.errors import RuleError
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import BomLine
from scopeiq.engine.design import FINAL, SiteModel
from scopeiq.reference.expressions import evaluate
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)


class TrunkPlan(dict):
    """count, vertical_ft, horizontal_ft, required_ft, length_ft, key, held (bool), reason"""


def trunk_plan(m: SiteModel, ref: ReferenceData) -> TrunkPlan:
    powered = m.new("radio", "air")
    n = math.ceil(len(powered) / 6) if powered else 0
    tp = TrunkPlan(count=n, powered_new=len(powered), vertical_ft=m.vertical_ft, horizontal_ft=m.horizontal_ft,
                   horizontal_basis=m.horizontal_basis, required_ft=None, length_ft=None, key=None, held=False, reason="")
    if not n:
        return tp
    if m.vertical_ft is None or m.horizontal_ft is None:
        tp.update(held=True, reason="Route length not documented (CBL-01) - trunk lines held, never assumed")
        return tp
    req = round(1.10 * (m.vertical_ft + m.horizontal_ft), 1)
    step = next(((L, k) for L, k in ref.trunk_steps if L >= req), None)
    if not step:
        tp.update(required_ft=req, held=True, reason=f"Required {req} ft exceeds the longest catalog trunk - engineering review")
        return tp
    tp.update(required_ft=req, length_ft=step[0], key=step[1])
    return tp


def _src(template: str, m: SiteModel, override: str | None = None) -> str:
    return override or (template or "").replace("{rfds_rev}", m.rfds_rev or "")


@log_call()
def generate_bom(m: SiteModel, ref: ReferenceData) -> tuple[list[BomLine], TrunkPlan]:
    rules = defaultdict(list)
    for r in ref.rows("kit_rules"):
        rules[r["TRIGGER_CODE"]].append(r)
    lines: list[BomLine] = []
    final = m.mode == FINAL
    rfds = f"RFDS {m.rfds_rev}" if m.rfds_rev else "RFDS"

    def fire(trigger: str, sector: str, variables: dict, *, device: str | None = None, parent: str = "", source: str | None = None,
             child_override: str | None = None, trace: dict | None = None):
        for r in rules.get(trigger, []):
            child = r["CHILD_KEY"]
            if child == "(device)":
                child = device
            elif child.endswith("*"):
                child = child_override
            if not child:
                continue
            try:
                qty = float(evaluate(r["QTY_EXPR"] or "0", variables))
                spare = float(evaluate(r["SPARE_EXPR"] or "0", variables))
            except Exception as exc:  # noqa: BLE001
                raise RuleError(f"Rule {r['RULE_ID']} expression failed: {exc}", details={"rule": r["RULE_ID"], "vars": variables}) from exc
            if qty <= 0 and spare <= 0:
                continue
            if child not in ref.catalog:
                raise RuleError(f"Rule {r['RULE_ID']} child {child} is not in the material catalog", details={"rule": r["RULE_ID"]})
            lines.append(BomLine(m.site_id, sector, child, qty, spare, "Remove" if trigger == "REMOVE_DEVICE" else "Install", r["RULE_ID"],
                                 _src(r.get("SOURCE_TEMPLATE", ""), m, source), parent, trace=dict(trace or {}, trigger=trigger)))

    # major equipment and removals
    for d in m.devices:
        if d.status == "New":
            fire("NEW_MAJOR", d.sector, {}, device=d.key, source=f"{rfds}; CD A-3", trace={"basis": d.basis, "position": d.position})
        elif d.status == "Remove":
            src = "Drone survey" if d.basis == "FIELD" else f"{rfds}; CD A-3"
            fire("REMOVE_DEVICE", d.sector, {}, device=d.key, source=src, trace={"basis": d.basis, "position": d.position})
    for bb in m.basebands:
        fire("NEW_MAJOR", "SITE", {}, device=bb, source=f"{rfds} Baseband & Power", trace={"basis": "RFDS"})
        fire("NEW_BASEBAND", "SITE", {}, parent=bb)
    # device packages
    antennas = {(d.sector, d.position): d for d in m.devices if d.kind in ("passive", "air") and d.status != "Remove"}
    for d in m.new():
        it = ref.catalog.get(d.key)
        if d.kind == "radio":
            fire("NEW_RADIO", d.sector, {"ports": it.rf_ports}, parent=d.key, trace={"position": d.position})
            fed = antennas.get((d.sector, d.position))
            if fed is None or fed.kind == "passive":
                fire("NEW_RADIO_TO_PASSIVE", d.sector, {"ports": it.rf_ports}, parent=d.key, trace={"position": d.position})
        elif d.kind == "air":
            fire("NEW_AAU", d.sector, {}, parent=d.key, trace={"position": d.position})
        elif d.kind == "passive":
            fire("NEW_PASSIVE", d.sector, {}, parent=d.key, trace={"position": d.position})
    # mounting, per sector with new equipment
    for sec in sorted({d.sector for d in m.new()}):
        fire("SECTOR_NEW_DEVICE", sec, {})
        if sec in m.new_frames:
            fire("SECTOR_NEW_FRAME", sec, {}, trace={"basis": "CD"})
            continue
        if m.rooftop and not m.sleds.get(sec, False):
            basis = m.sled_basis.get(sec, "CD")
            fire("ROOF_SECTOR_NO_SLED", sec, {}, source="Drone survey; CD A-3" if basis == "FIELD" else None, trace={"basis": basis})
            continue
        for pos in sorted({d.position for d in m.new("air", "passive") if d.sector == sec and d.position is not None}):
            if (sec, pos) not in m.pipes:
                basis = m.pipe_basis.get(sec, "CD")
                fire("POSITION_NO_PIPE", sec, {}, source="Drone survey; CD A-3" if basis == "FIELD" else None,
                     trace={"basis": basis, "position": pos})
    if final:
        for mod in m.ma_mods:
            fire("MA_REINFORCEMENT", mod["sector"] if mod["sector"] != "SITE" else "SITE", {"ma_qty": mod["qty"]}, trace={"basis": "MA"})
    # trunks
    tp = trunk_plan(m, ref)
    if tp["count"] and not tp["held"]:
        tsrc = "CD A-4; Drone survey (measured route)" if tp["horizontal_basis"] == "FIELD" else "CD A-4"
        v = {"powered_new": tp["powered_new"], "trunk_length_ft": tp["length_ft"]}
        n = tp["count"]
        fire("TRUNK", "SITE", v, child_override=tp["key"], source=tsrc, trace={"basis": tp["horizontal_basis"], "required_ft": tp["required_ft"]})
        for _ in range(n):
            fire("PER_TRUNK", "SITE", v)
        for _ in range(2 * n):                      # top + base OVP per trunk
            fire("PER_OVP", "SITE", v)
    # power
    added = sum(ref.catalog.get(d.key).power_w for d in m.new())
    removed = sum(ref.catalog.get(d.key).power_w for d in m.removed())
    fire("NET_DC_LOAD", "SITE", {"added_w": added, "removed_w": removed}, trace={"added_w": added, "removed_w": removed})
    fire("PER_SITE", "SITE", {})
    return consolidate(lines), tp


def consolidate(lines: list[BomLine]) -> list[BomLine]:
    """Sum identical lines (same sector, part, rule, parent, action) - one line per kit per sector."""
    out: dict[tuple, BomLine] = {}
    for l in lines:
        k = (l.sector, l.catalog_key, l.rule_id, l.parent_key, l.action)
        if k in out:
            out[k].design_qty += l.design_qty
            out[k].spare_qty += l.spare_qty
            out[k].trace.setdefault("instances", 1)
            out[k].trace["instances"] += 1
        else:
            out[k] = l
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "SITE": 9}
    return sorted(out.values(), key=lambda l: (order.get(l.sector, 5), l.action != "Install", l.rule_id, l.catalog_key))


def totals(lines: list[BomLine]) -> dict[tuple, float]:
    """(sector, key, action) -> total qty (design + spare)."""
    t: dict[tuple, float] = defaultdict(float)
    for l in lines:
        t[(l.sector, l.catalog_key, l.action)] += l.total_qty
    return dict(t)
