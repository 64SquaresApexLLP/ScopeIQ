"""Pipeline step 3 - Reconcile: cross-check the documents against each other and against the field
(guide 6.2 / 7.3). Every check is a row in CONSISTENCY_RULE (severity, outcome, target document, parameters)
so tolerances and outcomes change as data, not code; a rule that is inactive for the date or stream is skipped.

Governing sources: the RFDS governs RF (models, positions, azimuths, rad centers); the field (drone) governs
existing physical conditions (pipes, sleds, route lengths, what is really mounted); the MA/SA governs
structural requirements. Each finding names what governs and what the BOM therefore follows.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable

from scopeiq.common.ids import stable_id
from scopeiq.common.logging import get_logger, log_call
from scopeiq.config import get_settings
from scopeiq.domain import SECTOR_NAMES, ConfigItem, Discrepancy, SiteFacts
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)
CHECKS: list[Callable] = []


def check(fn: Callable) -> Callable:
    CHECKS.append(fn)
    return fn


def _cls(kind: str) -> str:
    return "radio" if kind == "radio" else "antenna" if kind in ("passive", "air") else kind


def _sec(s: str | None) -> str:
    return SECTOR_NAMES.get(s or "", s or "Site")


def _name(ref: ReferenceData, key: str | None) -> str:
    return ref.catalog.get(key).model if key and key in ref.catalog else (key or "unknown")


class Ctx:
    def __init__(self, facts: SiteFacts, ref: ReferenceData, stream: str):
        self.f, self.ref, self.stream = facts, ref, stream
        self.out: list[Discrepancy] = []
        st = get_settings()
        self.tol_az = float(st.get("engine.azimuth_tolerance_deg", 5))
        self.tol_rc = float(st.get("engine.rad_center_tolerance_ft", 2))
        self.tol_route = float(st.get("engine.route_tolerance_ft", 10))
        self.threshold = float(st.get("engine.extraction_confidence_threshold", 0.8))

    def add(self, rule_id: str, title: str, description: str, *, sector=None, position=None, key=None, expected=None, found=None,
            governing: str = "", sources=(), bom_impact: str = "", evidence=(), confidence: float = 1.0, sheet: str | None = None) -> Discrepancy | None:
        if not self.ref.rule_active(rule_id, self.stream):
            return None
        rule = self.ref.consistency_rule(rule_id)
        params = rule.get("PARAMS", {})
        d = Discrepancy(stable_id("DSC", self.f.site_id, rule_id, sector or "", position or "", key or "", title), self.f.site_id, rule_id,
                        rule["FAMILY"], rule["SEVERITY"], rule["OUTCOME"], title, description, sector, position, expected, found, governing,
                        [s for s in sources if s], rule["TARGET_DOC"], sheet or params.get("sheet", ""), bom_impact, list(evidence),
                        confidence=confidence)
        self.out.append(d)
        return d

    def frames_for(self, sector: str | None) -> list[str]:
        return [fr.path for fr in self.f.frames if fr.selected and (sector is None or fr.sector == sector)]

    @property
    def has_field(self) -> bool:
        return bool(self.f.field_items)

    def field_sectors(self) -> set[str]:
        return {i.sector for i in self.f.field_items}


# --------------------------------------------------------------------------- documents / extraction
@check
def doc_required(c: Ctx):
    rule = c.ref.consistency_rule("DOC-01")
    need = rule.get("PARAMS", {}).get("required", {}).get(c.stream, [])
    have = {d.doc_type for d in c.f.documents if d.status == "CURRENT"}
    have |= {"DRONE"} if any(t.startswith("DRONE") for t in have) else set()
    for t in need:
        if t not in have:
            c.add("DOC-01", f"{t} missing", f"The {c.stream} stream needs a {t} for this site and none is registered. "
                  "Scoping continues with what is available; dependent checks are skipped.", key=t, expected=t, found=None)


@check
def doc_duplicates(c: Ctx):
    for d in c.f.documents:
        if d.status == "DUPLICATE":
            c.add("DOC-02", f"Duplicate upload {d.file_name}", "Same file content is registered twice; the copy is ignored.",
                  key=d.file_name, found=d.rel_path)


@check
def low_confidence(c: Ctx):
    by_doc = defaultdict(list)
    for fld in c.f.fields:
        if fld.needs_review or fld.confidence < c.threshold:
            by_doc[fld.doc_id].append(fld)
    for doc_id, flds in by_doc.items():
        doc = next((d for d in c.f.documents if d.doc_id == doc_id), None)
        name = doc.file_name if doc else doc_id
        c.add("EXT-01", f"{len(flds)} value(s) need review in {name}",
              "Read below the confidence threshold or not matched to the catalog: " +
              "; ".join(f"{x.field_name}={x.value} ({x.confidence:.2f})" for x in flds[:12]) + (" ..." if len(flds) > 12 else ""),
              key=doc_id, found=[{"field": x.field_name, "value": str(x.value), "confidence": x.confidence, "page": x.page} for x in flds],
              sources=[doc.doc_type if doc else ""], confidence=min(x.confidence for x in flds))


# --------------------------------------------------------------------------- revisions / analyses
@check
def revisions(c: Ctx):
    cur = c.f.rfds_revision
    if cur and c.f.cd_rfds_reference and c.f.cd_rfds_reference != cur:
        c.add("REV-02", f"CD drawn from RFDS {c.f.cd_rfds_reference}, current is {cur}",
              f"CD general notes reference RFDS {c.f.cd_rfds_reference}; the current RFDS is {cur}. Redline the CD to the current RFDS.",
              expected=cur, found=c.f.cd_rfds_reference, governing="RFDS", sources=[f"CD {c.f.cd_revision} T-1", f"RFDS {cur}"], sheet="T-1")
    for a in (c.f.ma, c.f.sa):
        if a and a.rfds_revision and cur and a.rfds_revision != cur:
            c.add("REV-01", f"{a.kind} run on RFDS {a.rfds_revision}, current is {cur}",
                  f"{a.report_id} analysed RFDS {a.rfds_revision}. Request a re-run on {cur}.", key=a.kind,
                  expected=cur, found=a.rfds_revision, governing="RFDS", sources=[a.ref.label() if a.ref else a.kind])


def _final_devices(f: SiteFacts) -> list[ConfigItem]:
    return [i for i in f.rfds_final if i.is_device and i.status != "Remove"]


@check
def analyses(c: Ctx):
    ma, sa = c.f.ma, c.f.sa
    if sa and (sa.result == "FAIL" or (sa.capacity_pct or 0) > c.ref.consistency_rule("SA-01")["PARAMS"].get("max_capacity_pct", 100)):
        c.add("SA-01", f"Structure fails SA at {sa.capacity_pct:g}%",
              f"{sa.report_id}: {sa.result}, controlling member at {sa.capacity_pct:g}%. Structural modification design is needed "
              "before any new loading; this is outside BOM scope and is escalated (EHS alert + hold).",
              expected="<= 100%", found=f"{sa.capacity_pct:g}%", governing="SA", sources=[sa.ref.label() if sa.ref else "SA"],
              bom_impact="None (flag); site requirements add an SA-FAIL hold")
    if ma:
        lim = c.ref.consistency_rule("MA-01")["PARAMS"].get("max_capacity_pct", 100)
        after = ma.capacity_after_pct
        if ma.result == "FAIL" or ((ma.capacity_pct or 0) > lim and (after is None or after > lim)):
            c.add("MA-01", f"Mount over capacity ({ma.capacity_pct:g}%)", f"{ma.report_id}: {ma.result}.",
                  found=f"{ma.capacity_pct:g}%", governing="MA", sources=[ma.ref.label() if ma.ref else "MA"])
        if ma.modifications:
            cd_shows = any("REINFORC" in s.upper() or "MRK" in s.upper() for s in c.f.site.get("cd_scope_lines", []))
            if not cd_shows:
                mods = ", ".join(f"{_sec(m['sector'])} {m['kit_key'] or m['text']} x{m['qty']}" for m in ma.modifications)
                c.add("MNT-01", "MA modifications not shown on CD",
                      f"{ma.report_id} passes only with modifications ({mods}); the CD does not show them. Redline CD A-3 and add the kits to the BOM.",
                      expected=ma.modifications, found=None, governing="MA", sources=[ma.ref.label() if ma.ref else "MA", f"CD {c.f.cd_revision} A-3"],
                      bom_impact=f"+{sum(m['qty'] for m in ma.modifications)} {ma.modifications[0]['kit_key'] or 'kit'}")
        # LOAD-01: analysed loading vs final RFDS
        if ma.loading and c.f.rfds_final:
            want = Counter((i.sector, i.position, i.catalog_key) for i in _final_devices(c.f))
            got = Counter((i.sector, i.position, i.catalog_key) for i in ma.loading if i.status != "Remove")
            miss, extra = want - got, got - want
            if miss or extra:
                c.add("LOAD-01", "MA loading differs from final RFDS",
                      "Not analysed: " + ", ".join(f"{_sec(s)} pos {p} {_name(c.ref, k)}" for s, p, k in miss.elements()) +
                      ("; analysed but not on RFDS: " + ", ".join(f"{_sec(s)} pos {p} {_name(c.ref, k)}" for s, p, k in extra.elements()) if extra else ""),
                      expected=sorted(map(list, want.elements())), found=sorted(map(list, got.elements())), governing="RFDS",
                      sources=[ma.ref.label() if ma.ref else "MA", f"RFDS {c.f.rfds_revision}"])


# --------------------------------------------------------------------------- RFDS vs CD
@check
def rfds_vs_cd(c: Ctx):
    f = c.f
    if not f.rfds_final or not f.cd_items:
        return
    rf_src, cd_src = f"RFDS {f.rfds_revision}", f"CD {f.cd_revision}"
    for code, si in sorted(f.sectors.items()):
        a_r, a_c = si.azimuth.get("RFDS"), si.azimuth.get("CD")
        if a_r is not None and a_c is not None and abs((a_r - a_c + 180) % 360 - 180) > c.ref.consistency_rule("RFC-01")["PARAMS"].get("tolerance_deg", 0):
            fa = si.azimuth.get("FIELD")
            c.add("RFC-01", f"{_sec(code)} azimuth RFDS {a_r:g} vs CD {a_c:g}",
                  f"RFDS sets {_sec(code)} to {a_r:g} deg; the CD shows {a_c:g} deg" + (f" and the field measures {fa:g} deg" if fa is not None else "") +
                  ". RFDS governs RF: confirm the re-orientation with the RF engineer and redline the CD.",
                  sector=code, expected=a_r, found=a_c, governing="RFDS", sources=[f"{rf_src} Final Config", f"{cd_src} A-3"],
                  evidence=c.frames_for(code), bom_impact="None", sheet="A-3")
    # devices: compare by (sector, class) so a position swap is reported once, not as missing + extra
    rf = [i for i in f.rfds_final if i.is_device and i.status != "Remove"]
    cd = [i for i in f.cd_items if i.is_device and i.status != "Remove"]
    for sec in sorted({i.sector for i in rf + cd}):
        r_s = [i for i in rf if i.sector == sec]
        c_s = [i for i in cd if i.sector == sec]
        r_keys, c_keys = Counter(i.catalog_key for i in r_s), Counter(i.catalog_key for i in c_s)
        for k in (r_keys - c_keys).elements():
            it = next(i for i in r_s if i.catalog_key == k)
            c.add("RFC-02", f"{_sec(sec)} {_name(c.ref, k)} on RFDS, not on CD",
                  f"RFDS {f.rfds_revision} has {it.status.lower()} {_name(c.ref, k)} at {_sec(sec)} position {it.position}; the CD omits it. "
                  "RFDS governs: the BOM includes it and its dependent package; raise an RFI and redline CD A-3/A-4.",
                  sector=sec, position=it.position, key=k, expected=k, found=None, governing="RFDS",
                  sources=[f"{rf_src} Final Config", f"{cd_src} A-3/A-4"], bom_impact=f"+1 {k} and dependent package", sheet="A-3")
        for k in (c_keys - r_keys).elements():
            it = next(i for i in c_s if i.catalog_key == k)
            c.add("RFC-03", f"{_sec(sec)} {_name(c.ref, k)} on CD, not on RFDS",
                  f"The CD shows {_name(c.ref, k)} at {_sec(sec)} position {it.position}; RFDS {f.rfds_revision} does not. RFDS governs: not in the BOM.",
                  sector=sec, position=it.position, key=k, expected=None, found=k, governing="RFDS",
                  sources=[f"{cd_src} {it.ref.page if it.ref else 'A-3'}", rf_src], sheet="A-3")
        # positions of equipment present on both
        moved = []
        for k in set(r_keys) & set(c_keys):
            rp = sorted(i.position for i in r_s if i.catalog_key == k)
            cp = sorted(i.position for i in c_s if i.catalog_key == k)
            if rp != cp and len(rp) == len(cp):
                moved.append((k, rp, cp))
        if moved:
            c.add("RFC-04", f"{_sec(sec)} positions differ RFDS vs CD",
                  f"{_sec(sec)}: " + "; ".join(f"{_name(c.ref, k)} RFDS pos {'/'.join(map(str, rp))} vs CD pos {'/'.join(map(str, cp))}" for k, rp, cp in moved) +
                  ". RFDS governs placement: raise an RFI and redline CD A-3.",
                  sector=sec, expected={k: rp for k, rp, _ in moved}, found={k: cp for k, _, cp in moved}, governing="RFDS",
                  sources=[f"{rf_src} Final Config", f"{cd_src} A-3"], bom_impact="None", sheet="A-3")
        # rad centers on matched devices
        tol = c.ref.consistency_rule("RFC-05")["PARAMS"].get("tolerance_ft", 0)
        diffs = []
        for r in r_s:
            m = next((x for x in c_s if x.catalog_key == r.catalog_key and x.position == r.position), None)
            if m and r.rad_center_ft is not None and m.rad_center_ft is not None and abs(r.rad_center_ft - m.rad_center_ft) > tol and r.kind != "radio":
                diffs.append((r.catalog_key, r.position, r.rad_center_ft, m.rad_center_ft))
        if diffs:
            c.add("RFC-05", f"{_sec(sec)} rad center RFDS vs CD",
                  "; ".join(f"{_name(c.ref, k)} pos {p}: RFDS {a:g} ft vs CD {b:g} ft" for k, p, a, b in diffs),
                  sector=sec, expected=[d[2] for d in diffs], found=[d[3] for d in diffs], governing="RFDS",
                  sources=[rf_src, f"{cd_src} A-2/A-4"], sheet="A-2")


# --------------------------------------------------------------------------- CD vs field
def _present_design(f: SiteFacts) -> list[ConfigItem]:
    """Equipment the CD says is physically there today (existing or to be removed); RFDS existing as fallback."""
    cd = [i for i in f.cd_items if i.is_device and i.status in ("Existing", "Remove")]
    return cd or [i for i in f.rfds_existing if i.is_device]


@check
def cd_vs_field(c: Ctx):
    f = c.f
    if not c.has_field:
        return
    fsrc = f"Drone survey ({'vendor measurements' if f.field_method == 'VENDOR_CSV' else 'point cloud'})"
    cd_src = f"CD {f.cd_revision}"
    covered = c.field_sectors()
    rooftop = f.is_rooftop
    no_sled = set()
    # FLD-05 sleds
    for code, si in sorted(f.sectors.items()):
        if rooftop and si.sled.get("CD") and si.sled.get("FIELD") is False:
            no_sled.add(code)
            c.add("FLD-05", f"{_sec(code)} roof sled not found in field",
                  f"CD A-3 shows an existing roof sled for {_sec(code)}; the drone survey finds no sled (nor pipes) there. "
                  "Redline CD A-3 and add a roof sled to the BOM.", sector=code, expected="existing sled", found="none",
                  governing="FIELD", sources=[f"{cd_src} A-3", fsrc], evidence=c.frames_for(code), bom_impact="+1 SLED")
    # FLD-04 azimuth (field vs CD as drawn; RFDS vs CD is RFC-01)
    for code, si in sorted(f.sectors.items()):
        fa, ca = si.azimuth.get("FIELD"), si.azimuth.get("CD", si.azimuth.get("RFDS"))
        if fa is not None and ca is not None and abs((fa - ca + 180) % 360 - 180) > c.tol_az:
            ra = si.azimuth.get("RFDS", ca)
            c.add("FLD-04", f"{_sec(code)} measured at {fa:.0f} deg, CD {ca:g} deg",
                  f"Drone survey measures {_sec(code)} antennas facing {fa:.0f} deg; the CD shows {ca:g} deg "
                  f"({abs((fa - ca + 180) % 360 - 180):.0f} deg off, tolerance {c.tol_az:g}). Design azimuth is {ra:g} deg: "
                  "raise an RFI and add the re-orientation to the scope of work.",
                  sector=code, expected=ca, found=round(fa, 1), governing="RFDS", sources=[f"{cd_src} A-3", fsrc],
                  evidence=c.frames_for(code), bom_impact="None (service: re-orient sector)")
    # FLD-02 pipes
    field_pipes = {(i.sector, i.position) for i in f.field_items if i.kind == "pipe"}
    for it in f.cd_items:
        if it.kind == "pipe" and it.status == "Existing" and not it.attrs.get("inferred") and it.sector in covered | no_sled:
            if (it.sector, it.position) not in field_pipes and it.sector not in no_sled:
                spare = " spare" if it.attrs.get("spare") else ""
                c.add("FLD-02", f"{_sec(it.sector)} position {it.position} existing{spare} pipe missing in field",
                      f"CD A-3 shows an existing{spare} mount pipe at {_sec(it.sector)} position {it.position}; the drone survey finds no pipe. "
                      "Redline CD A-3; a mount pipe kit is needed if new equipment goes there.",
                      sector=it.sector, position=it.position, key="PIPE", expected="pipe", found="none", governing="FIELD",
                      sources=[f"{cd_src} A-3", fsrc], evidence=c.frames_for(it.sector), bom_impact="+1 PIPE if position is used")
    # FLD-01 / FLD-07 devices, compared per (sector, position, class) by count, then by model
    design = _present_design(f)
    fld = [i for i in f.field_items if i.is_device]
    keys = sorted({(i.sector, i.position, _cls(i.kind)) for i in design + fld if i.sector in covered}, key=str)
    for sec, pos, cl in keys:
        d_here = [i for i in design if i.sector == sec and i.position == pos and _cls(i.kind) == cl]
        f_here = [i for i in fld if i.sector == sec and i.position == pos and _cls(i.kind) == cl]
        dk, fk = Counter(i.catalog_key for i in d_here), Counter(i.catalog_key for i in f_here)
        if len(f_here) > len(d_here):
            extra = [i for i in f_here if not i.attrs.get("matched_design")] or f_here[len(d_here):]
            for i in extra[: len(f_here) - len(d_here)]:
                alike = i.attrs.get("look_alikes") or []
                model = _name(c.ref, i.catalog_key) + (f" (or look-alike {', '.join(_name(c.ref, a) for a in alike)})" if alike else "")
                c.add("FLD-01", f"Unrecorded {cl} at {_sec(sec)} position {pos}",
                      f"Drone survey finds a {cl} ({model}, {i.confidence:.0%} confidence) at {_sec(sec)} position {pos} that neither the CD nor "
                      "the RFDS records. Raise an RFI; it is not in the final design, so the BOM adds a removal line.",
                      sector=sec, position=pos, key=i.catalog_key, expected=None, found=i.catalog_key, governing="FIELD",
                      sources=[fsrc, f"{cd_src} A-3", f"RFDS {f.rfds_revision}"], evidence=c.frames_for(sec) + [i.attrs.get("object_id", "")],
                      bom_impact=f"+1 Remove {i.catalog_key}", confidence=i.confidence)
        elif len(f_here) < len(d_here):
            missing = list((dk - fk).elements())[: len(d_here) - len(f_here)] or [d_here[-1].catalog_key]
            for k in missing:
                c.add("FLD-07", f"{_sec(sec)} position {pos} {_name(c.ref, k)} not found in field",
                      f"The CD shows {_name(c.ref, k)} at {_sec(sec)} position {pos}; the drone survey does not find it. Confirm before removal "
                      "lines or reuse are scoped.", sector=sec, position=pos, key=k, expected=k, found=None, governing="FIELD",
                      sources=[f"{cd_src} A-3", fsrc], evidence=c.frames_for(sec))
    # FLD-03 rad center of existing antennas (one finding per site, listing sectors)
    rc_diffs = []
    for i in fld:
        if _cls(i.kind) != "antenna" or i.rad_center_ft is None:
            continue
        m = next((d for d in design if d.sector == i.sector and d.position == i.position and d.catalog_key == i.catalog_key), None)
        m = m or next((d for d in f.rfds_existing if d.sector == i.sector and d.position == i.position and d.catalog_key == i.catalog_key), None)
        drc = m.rad_center_ft if m and m.rad_center_ft is not None else None
        if drc is None and m:
            drc = next((r.rad_center_ft for r in f.rfds_final if r.sector == i.sector and r.position == i.position and r.catalog_key == i.catalog_key), None)
        if drc is not None and abs(round(i.rad_center_ft) - drc) > c.tol_rc:
            rc_diffs.append((i.sector, i.position, i.catalog_key, drc, i.rad_center_ft))
    if rc_diffs:
        avg = sum(d[4] - d[3] for d in rc_diffs) / len(rc_diffs)
        c.add("FLD-03", f"Existing antennas measured {abs(avg):.0f} ft {'lower' if avg < 0 else 'higher'} than drawn",
              f"{len(rc_diffs)} existing antenna(s) measure {rc_diffs[0][4]:.0f} ft rad center vs {rc_diffs[0][3]:g} ft on the CD/RFDS "
              f"(tolerance {c.tol_rc:g} ft). Raise an RFI and redline the CD elevation; trunk length is recomputed from the design rad center.",
              expected=sorted({d[3] for d in rc_diffs}), found=sorted({round(d[4], 1) for d in rc_diffs}), governing="FIELD",
              sources=[f"{cd_src} A-2", fsrc], evidence=c.frames_for(None)[:3], bom_impact="None unless the trunk step changes")
    # FLD-06 route length
    cdt, ft = f.trunks.get("CD"), f.trunks.get("FIELD")
    if cdt and ft and cdt.horizontal_ft is not None and ft.horizontal_ft is not None and abs(cdt.horizontal_ft - ft.horizontal_ft) > c.tol_route:
        c.add("FLD-06", f"Cable route measured {ft.horizontal_ft:.0f} ft, CD {cdt.horizontal_ft:g} ft",
              f"Drone survey measures the cabinet-to-structure route at {ft.horizontal_ft:.1f} ft; the CD A-4 cable schedule uses "
              f"{cdt.horizontal_ft:g} ft (tolerance {c.tol_route:g} ft). Trunk length is recomputed from the measured route; redline CD A-4.",
              expected=cdt.horizontal_ft, found=ft.horizontal_ft, governing="FIELD", sources=[f"{cd_src} A-4 cable schedule", fsrc],
              evidence=c.frames_for(None)[:2], bom_impact="Trunk length step and hangers recomputed")


@check
def cable_documented(c: Ctx):
    f = c.f
    new_powered = [i for i in f.rfds_final if i.status == "New" and i.kind in ("radio", "air")]
    if not new_powered:
        return
    cdt, ft = f.trunks.get("CD"), f.trunks.get("FIELD")
    if not ((cdt and cdt.horizontal_ft is not None) or (ft and ft.horizontal_ft is not None)):
        c.add("CBL-01", "Trunk route length not documented",
              "New powered equipment needs hybrid trunks but no route length is on the CD or measured in the field. "
              "The length is never assumed: the trunk line is held until the A&E answers.", governing="CD",
              sources=[f"CD {f.cd_revision} A-4"], bom_impact="Trunk lines held")


@log_call()
def reconcile(facts: SiteFacts, ref: ReferenceData, *, stream: str | None = None) -> list[Discrepancy]:
    c = Ctx(facts, ref, stream or facts.project.get("stream", "BOM"))
    for fn in CHECKS:
        try:
            fn(c)
        except Exception:  # noqa: BLE001 - one broken check must not hide the others
            log.exception("check %s failed", fn.__name__, extra={"site_id": facts.site_id})
            facts.warnings.append(f"reconcile check {fn.__name__} failed - see error log")
    log.info("reconcile: %d discrepancies %s", len(c.out), dict(Counter(d.rule_id for d in c.out)), extra={"site_id": facts.site_id})
    return c.out
