"""Pipeline step 6 - Estimate: service drivers (FPP codes), site requirements, EHS alerts, cost and cycle time.

Drivers come from the equipment delta and the BOM through SERVICE_DRIVER_MATRIX (delta action x equipment
class -> driver code); prices come from RATE_CARD (market + service provider override, wildcard fallback);
access/rigging needs come from SITE_REQUIREMENT_RULE (first match by priority, plus the SA-FAIL escalation rule);
cycle time from CYCLE_TIME_PARAM. All of it is reference data; all rates are illustrative.
"""
from __future__ import annotations

from collections import Counter

from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import BomLine, DeltaLine, Discrepancy, DriverLine, SiteFacts
from scopeiq.engine.bom import TrunkPlan
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)

BOM_CLASS = {"PIPE": "pipe", "FRAME": "frame", "SLED": "sled", "MRK": "mrk", "RECT3K": "rectifier", "GBAR": "ground_bar"}


def _driver_for(ref: ReferenceData, action: str, eq_class: str) -> dict | None:
    return next((r for r in ref.rows("service_driver_matrix") if r["DELTA_ACTION"] == action and r["EQUIPMENT_CLASS"] == eq_class), None)


@log_call()
def site_requirements(facts: SiteFacts, delta: list[DeltaLine], ref: ReferenceData) -> dict:
    structure = str(facts.site.get("structure_type") or "")
    height = float(facts.site.get("height_ft") or facts.site.get("rfds_structure_height_ft") or 0)
    new_dev = [d for d in delta if d.action == "NEW" and d.kind in ("passive", "air", "radio")]
    has_aau = any(d.kind == "air" for d in new_dev)
    load = len(new_dev) * ref.cycle_param("default_device_weight_lb", 60)
    match = None
    for r in sorted(ref.rows("site_requirement_rules"), key=lambda r: int(r["PRIORITY"])):
        if r["RULE_ID"] == "REQ-SA-FAIL":
            continue
        if r["STRUCTURE_TYPE"] not in ("*", structure):
            continue
        if not (float(r["MIN_HEIGHT_FT"]) <= height <= float(r["MAX_HEIGHT_FT"])):
            continue
        if load < float(r["MIN_NEW_LOAD_LB"] or 0):
            continue
        if r["REQUIRES_AAU"] == "Y" and not has_aau or r["REQUIRES_AAU"] == "N" and has_aau:
            continue
        match = r
        break
    out = {"rule_id": match["RULE_ID"] if match else None, "access_method": match["ACCESS_METHOD"] if match else "CLIMB",
           "crane_days": float(match["CRANE_DAYS"]) if match else 0, "manlift_days": float(match["MANLIFT_DAYS"]) if match else 0,
           "rigging_class": match["RIGGING_CLASS"] if match else "II", "ehs_alerts": [], "hold": False,
           "inputs": {"structure": structure, "height_ft": height, "new_devices": len(new_dev), "new_load_lb": load, "has_aau": has_aau}}
    if match and match["EHS_ALERT"]:
        out["ehs_alerts"].append({"rule_id": match["RULE_ID"], "severity": "HIGH", "text": match["EHS_ALERT"]})
    sa = facts.sa
    if sa and (sa.result == "FAIL" or (sa.capacity_pct or 0) > 100):
        r = next((x for x in ref.rows("site_requirement_rules") if x["RULE_ID"] == "REQ-SA-FAIL"), None)
        if r:
            out["hold"] = True
            out["ehs_alerts"].append({"rule_id": "REQ-SA-FAIL", "severity": "CRITICAL", "text": r["EHS_ALERT"]})
    return out


@log_call()
def build_drivers(facts: SiteFacts, delta: list[DeltaLine], bom: list[BomLine], tp: TrunkPlan, reqs: dict,
                  discrepancies: list[Discrepancy], ref: ReferenceData) -> list[DriverLine]:
    market = facts.site.get("market") or facts.site.get("rfds_market") or "DFW"
    sp = facts.project.get("cx_sp") or "*"
    lines: list[DriverLine] = []

    def add(action: str, eq_class: str, qty: float, basis: str, sector: str | None = None):
        if qty <= 0:
            return
        drv = _driver_for(ref, action, eq_class)
        if not drv:
            log.warning("no service driver for %s/%s", action, eq_class, extra={"site_id": facts.site_id})
            return
        rate = ref.rate(market, sp, drv["DRIVER_CODE"])
        lines.append(DriverLine(facts.site_id, drv["DRIVER_CODE"], drv["DESCRIPTION"], qty, drv["UOM"], rate or 0.0, basis, sector))

    actions = {"NEW": "NEW", "REMOVED": "REMOVED", "RELOCATED": "RELOCATED", "REUSED": "REUSED"}
    for (sec, act, kind), n in sorted(Counter((d.sector, d.action, d.kind) for d in delta if d.action in actions).items(), key=str):
        add(actions[act], kind, n, f"Equipment delta: {n} x {act.lower()} {kind}", None if sec == "SITE" else sec)
    if tp.get("count") and not tp.get("held"):
        cls = "trunk_le_200" if tp["length_ft"] <= 200 else "trunk_gt_200"
        add("NEW", cls, tp["count"], f"{tp['count']} x hybrid trunk {tp['length_ft']} ft")
        add("NEW", "ovp", 2 * tp["count"], "Top + base OVP per trunk")
    for key, cls in BOM_CLASS.items():
        for sec in sorted({l.sector for l in bom if l.catalog_key == key}):
            q = sum(l.design_qty for l in bom if l.catalog_key == key and l.sector == sec)
            add("NEW", cls, q, f"BOM {key} x {q:g}", None if sec == "SITE" else sec)
    # re-orientation: field azimuth differs from the design (RFDS) azimuth beyond tolerance
    for code, si in sorted(facts.sectors.items()):
        fa, ra = si.azimuth.get("FIELD"), si.azimuth.get("RFDS")
        if fa is not None and ra is not None and abs((fa - ra + 180) % 360 - 180) > 5:
            add("ADJUST", "sector", 1, f"Field {fa:.0f} deg vs design {ra:g} deg", code)
    add("REQUIREMENT", "crane", reqs.get("crane_days", 0), f"Site requirement {reqs.get('rule_id')}")
    add("REQUIREMENT", "manlift", reqs.get("manlift_days", 0), f"Site requirement {reqs.get('rule_id')}")
    if reqs.get("rigging_class"):
        add("REQUIREMENT", "rigging_plan", 1, f"Rigging class {reqs['rigging_class']}")
    add("REQUIREMENT", "site", 1, "One per site")
    return lines


@log_call()
def estimate(facts: SiteFacts, delta: list[DeltaLine], bom: list[BomLine], tp: TrunkPlan, reqs: dict, drivers: list[DriverLine],
             ref: ReferenceData) -> dict:
    p = ref.cycle_param
    new = sum(1 for d in delta if d.action == "NEW" and d.kind != "baseband")
    rem = sum(1 for d in delta if d.action == "REMOVED")
    frames_sleds = sum(l.design_qty for l in bom if l.catalog_key in ("FRAME", "SLED"))
    mrk = sum(l.design_qty for l in bom if l.catalog_key == "MRK")
    days = (p("base_days") + p("per_major_install") * new + p("per_major_removal") * rem + p("per_trunk") * (tp.get("count") or 0)
            + p("per_frame_or_sled") * frames_sleds + p("per_mrk") * mrk + p("crane_day") * reqs.get("crane_days", 0) + p("integration_days"))
    days *= 1 + p("weather_contingency_pct") / 100
    if reqs.get("hold"):
        days += p("sa_fail_hold_days")
    material = sum(ref.catalog.get(l.catalog_key).unit_cost * l.total_qty for l in bom if l.action == "Install")
    services = sum(d.amount for d in drivers)
    return {"cycle_days": round(days, 1), "services_usd": round(services, 2), "material_usd": round(material, 2),
            "total_usd": round(services + material, 2), "new_devices": new, "removed_devices": rem, "illustrative": True}
