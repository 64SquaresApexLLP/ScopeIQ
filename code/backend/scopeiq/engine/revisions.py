"""REV 0 validation and the REV 1 BOM.

REV 0 is the Ericsson tool's preliminary BOM built from the CD as drawn. Running the same kitting rules on
the AS_DRAWN model gives what REV 0 should be, so any difference is a tool error (BOM-01..05, reason
RC-REV0-ERR). The FINAL model differs from AS_DRAWN only because of discrepancies (field conditions, RFDS
over CD, MA requirements); those changes carry the discrepancy's reason code. REV 1 = FINAL, and every
changed line explains which of the two it came from.
"""
from __future__ import annotations

from collections import defaultdict

from scopeiq.common.ids import stable_id
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import SECTOR_NAMES, BomLine, Discrepancy, Rev0Line
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)

TRUNK_RULES = ("R-TRK-", "R-OVP-")


def _sec(s: str) -> str:
    return SECTOR_NAMES.get(s, "Site")


def _agg(lines, *, rev0: bool):
    qty, rows = defaultdict(float), defaultdict(int)
    for l in lines:
        key = (l.sector, l.catalog_key or l.model, l.action if not rev0 else ("Remove" if l.action.lower().startswith("rem") else "Install"),
               l.rule_id)
        qty[key] += (l.design_qty + l.spare_qty)
        rows[key] += 1 if rev0 else int(l.trace.get("instances", 1))
    return qty, rows


@log_call()
def validate_rev0(site_id: str, rev0: list[Rev0Line], as_drawn: list[BomLine], ref: ReferenceData, stream: str = "BOM") -> list[Discrepancy]:
    if not rev0:
        return []
    gq, gr = _agg(as_drawn, rev0=False)
    rq, rr = _agg(rev0, rev0=True)
    issues: list[dict] = []
    paired_missing = set()
    # non-approved substitutes first (same sector + rule as a missing approved line)
    for k in rq:
        if k in gq:
            continue
        sec, part, act, rule = k
        it = ref.catalog.get(part) if part in ref.catalog else None
        if it and not it.approved:
            sub = next((g for g in gq if g not in rq and g[0] == sec and g[3] == rule), None)
            if sub:
                paired_missing.add(sub)
            issues.append(dict(rule="BOM-04", group=("BOM-04", part, sub[1] if sub else ""), sector=sec, part=part, replace=sub[1] if sub else None,
                               rev0=rq[k], gen=gq.get(sub, 0) if sub else 0, rule_id=rule))
    for k in sorted(set(gq) | set(rq), key=str):
        if k in paired_missing or (k in rq and k not in gq and any(i["part"] == k[1] and i["sector"] == k[0] for i in issues)):
            continue
        sec, part, act, rule = k
        g, r = gq.get(k, 0), rq.get(k, 0)
        if g == r:
            continue
        trunk = rule.startswith(TRUNK_RULES)
        if r == 0:
            code = "BOM-01"
        elif g == 0:
            code = "BOM-05"
        elif rr[k] > gr.get(k, 1) and abs(r - g * rr[k] / max(gr.get(k, 1), 1)) < 1e-6:
            code = "BOM-03"
        else:
            code = "BOM-02"
        issues.append(dict(rule=code, group=(code, part), sector=sec, part=part, rev0=r, gen=g, rule_id=rule, action=act, trunk=trunk))
    # a wrong trunk count drives the whole trunk package: report it once
    if any(i.get("trunk") and i["rule_id"] == "R-TRK-01" for i in issues):
        for i in issues:
            if i.get("trunk") and i["rule"] in ("BOM-01", "BOM-02"):
                i["group"] = ("TRUNK",)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for i in issues:
        groups[i["group"]].append(i)
    out = []
    for g, items in groups.items():
        first = items[0]
        code = "BOM-02" if g == ("TRUNK",) else first["rule"]
        if not ref.rule_active(code, stream):
            continue
        rule = ref.consistency_rule(code)
        detail = "; ".join(f"{_sec(i['sector'])} {_name(ref, i['part'])} ({i['rule_id']}): REV 0 {i['rev0']:g} vs rules {i['gen']:g}" for i in items)
        if g == ("TRUNK",):
            hyb = next((i for i in items if i["rule_id"] == "R-TRK-01"), None)
            title = (f"REV 0 trunk count {hyb['rev0']:g} vs {hyb['gen']:g} required" if hyb else "REV 0 trunk package quantities differ")
        elif code == "BOM-04":
            title = f"Non-approved {_name(ref, first['part'])} used" + (f" instead of {_name(ref, first['replace'])}" if first.get("replace") else "")
        elif code == "BOM-03":
            title = f"Duplicate {_name(ref, first['part'])} line ({', '.join(_sec(i['sector']) for i in items)})"
        elif code == "BOM-01":
            title = f"{_name(ref, first['part'])} missing from REV 0 ({', '.join(sorted({_sec(i['sector']) for i in items}))})"
        elif code == "BOM-05":
            title = f"Extra {_name(ref, first['part'])} on REV 0"
        else:
            title = f"{_name(ref, first['part'])} quantity differs ({', '.join(sorted({_sec(i['sector']) for i in items}))})"
        delta = sum(i["gen"] - i["rev0"] for i in items if i["part"] == first["part"])
        out.append(Discrepancy(stable_id("DSC", site_id, code, *map(str, g)), site_id, code, rule["FAMILY"], rule["SEVERITY"], rule["OUTCOME"],
                               title, f"REV 0 differs from the kitting rules applied to the CD as drawn: {detail}. Corrected on REV 1 (RC-REV0-ERR).",
                               sector=first["sector"] if len({i['sector'] for i in items}) == 1 else None,
                               expected=[{"sector": i["sector"], "part": i.get("replace") or i["part"], "qty": i["gen"], "rule": i["rule_id"]} for i in items],
                               found=[{"sector": i["sector"], "part": i["part"], "qty": i["rev0"], "rule": i["rule_id"]} for i in items],
                               governing="KIT_RULES", sources=["BOM REV 0", "Kit rules on CD as drawn"], target_doc="BOM_REV0",
                               bom_impact=("Trunk package corrected" if g == ("TRUNK",) else
                                           f"Swap {sum(i['rev0'] for i in items):g} x {first['part']} for {first.get('replace')}" if code == "BOM-04"
                                           else f"{delta:+g} {first['part']}")))
    log.info("REV 0 check: %d finding(s)", len(out), extra={"site_id": site_id})
    return out


def _name(ref: ReferenceData, key: str | None) -> str:
    return ref.catalog.get(key).model if key and key in ref.catalog else (key or "?")


KEY_TO_RULE = {"PIPE": ("FLD-02",), "SLED": ("FLD-05",), "MRK": ("MNT-01",), "HANGER": ("FLD-06",), "GKT": ("FLD-06",)}


@log_call()
def build_rev1(site_id: str, rev0: list[Rev0Line], as_drawn: list[BomLine], final: list[BomLine], discrepancies: list[Discrepancy]) -> list[dict]:
    """Change list REV 0 -> REV 1 per (sector, part, action) with the reason for each part of the change."""
    def tot(lines, is_rev0=False):
        t = defaultdict(float)
        for l in lines:
            act = ("Remove" if l.action.lower().startswith("rem") else "Install") if is_rev0 else l.action
            t[(l.sector, l.catalog_key or getattr(l, "model", ""), act)] += l.design_qty + l.spare_qty
        return t
    r0, ad, fn = tot(rev0, True), tot(as_drawn), tot(final)
    bom_disc = [d for d in discrepancies if d.rule_id.startswith("BOM-")]
    design_disc = [d for d in discrepancies if not d.rule_id.startswith(("BOM-", "EXT-", "DOC-")) and d.bom_impact and not d.bom_impact.startswith("None")]
    changes = []
    for k in sorted(set(r0) | set(ad) | set(fn), key=str):
        sec, part, act = k
        a, b, c = r0.get(k, 0), ad.get(k, 0), fn.get(k, 0)
        if a == c:
            continue
        reasons = []
        if b != a:
            ids = [d.disc_id for d in bom_disc if any(x.get("part") == part for x in (d.expected or []) + (d.found or []))]
            reasons.append({"reason_code": "RC-REV0-ERR", "qty": b - a, "disc_ids": ids})
        if c != b:
            rules = KEY_TO_RULE.get(part, ())
            if part.startswith("HYB"):
                rules = ("FLD-06",)
            ids = [d.disc_id for d in design_disc if d.rule_id in rules]
            if not ids and act == "Remove":
                ids = [d.disc_id for d in design_disc if d.rule_id == "FLD-01" and d.found == part]
            if not ids:
                ids = [d.disc_id for d in design_disc if d.sector in (sec, None) and d.rule_id in ("RFC-02", "MNT-01", "FLD-05", "FLD-02", "FLD-06")]
            rc = "RC-MA-REQ" if part == "MRK" else "RC-DOC-CONFLICT" if any(i.startswith("DSC") and next(
                (d for d in design_disc if d.disc_id == i and d.rule_id.startswith("RFC")), None) for i in ids) else "RC-FIELD-COND"
            reasons.append({"reason_code": rc, "qty": c - b, "disc_ids": ids})
        changes.append({"site_id": site_id, "sector": sec, "part": part, "action": act, "rev0_qty": a, "rev1_qty": c, "delta": c - a, "reasons": reasons})
    log.info("REV 1: %d changed line(s) vs REV 0", len(changes), extra={"site_id": site_id})
    return changes
