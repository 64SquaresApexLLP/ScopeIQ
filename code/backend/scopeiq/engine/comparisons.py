"""Stage 3 comparison log: which object of which document was compared with which object of which other document,
and what came out. It is a readable record of the checks `reconcile` runs: every check names its two sides (with the
file names), lists the pairs it compared and marks the pairs that disagree. A pair that disagrees is the same
finding `reconcile` raised (Discrepancy), so each mismatch row links to a discrepancy and nothing is invented here.
"""
from __future__ import annotations

from collections import Counter

from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings
from scopeiq.domain import SECTOR_NAMES, ConfigItem, Discrepancy, SiteFacts
from scopeiq.engine.reconcile import _cls, _present_design
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)
KIND_LABEL = {"passive": "Antenna", "air": "Active antenna", "radio": "Radio", "pipe": "Mount pipe", "sled": "Roof sled"}


def _sec(code: str | None) -> str:
    return SECTOR_NAMES.get(code or "", code or "Site")


def _model(ref: ReferenceData, it: ConfigItem) -> str:
    base = ref.catalog.get(it.catalog_key).model if it.catalog_key and it.catalog_key in ref.catalog else (it.model_text or it.catalog_key or "unknown")
    return base if it.kind == "radio" and base.lower().startswith("radio") else f"{KIND_LABEL.get(it.kind, 'Item')} {base}"


def _list(ref: ReferenceData, items: list[ConfigItem]) -> str:
    return ", ".join(sorted(_model(ref, i) for i in items)) if items else "not present"


class _Log:
    def __init__(self, facts: SiteFacts, ref: ReferenceData, discs: list[Discrepancy], stream: str):
        self.f, self.ref, self.stream = facts, ref, stream
        self.checks: list[dict] = []
        self.by_rule: dict[str, list[Discrepancy]] = {}
        for d in discs:
            self.by_rule.setdefault(d.rule_id, []).append(d)
        st = get_settings()
        self.tol_az = float(st.get("engine.azimuth_tolerance_deg", 5))
        self.tol_rc = float(st.get("engine.rad_center_tolerance_ft", 2))
        self.tol_route = float(st.get("engine.route_tolerance_ft", 10))
        self.threshold = float(st.get("engine.extraction_confidence_threshold", 0.8))

    # ------------------------------------------------------------------ sources
    def files(self, *doc_types: str, fmt: str | None = None) -> list[str]:
        cur = [d for d in self.f.documents if d.doc_type in doc_types and d.status == "CURRENT" and (fmt is None or d.file_format == fmt)]
        top = max((d.revision_rank for d in cur), default=0)
        return sorted(d.file_name for d in cur if d.revision_rank == top)

    def cd_files(self) -> list[str]:
        return self.files("CD", fmt="DXF" if str(self.f.cd_method).startswith("DXF") else "PDF")

    def drone_files(self) -> list[str]:
        return self.files("DRONE_VENDOR" if self.f.field_method == "VENDOR_CSV" else "DRONE_POINTCLOUD")

    def side(self, label: str, files: list[str], obj: str) -> dict:
        return {"label": label, "files": files, "object": obj}

    # ------------------------------------------------------------------ recording
    def hit(self, rules: tuple[str, ...], sector: str | None = None, position: int | None = None) -> Discrepancy | None:
        for r in rules:
            for d in self.by_rule.get(r, []):
                if (sector is None or d.sector in (None, sector)) and (position is None or d.position in (None, position)):
                    return d
        return None

    def row(self, where: str, left: str, right: str, rules: tuple[str, ...], *, sector=None, position=None, bad: bool | None = None) -> dict:
        d = self.hit(rules, sector, position) if bad is None or bad else None
        mismatch = bool(d) if bad is None else bad
        return {"where": where, "left": left, "right": right, "result": "MISMATCH" if mismatch else "MATCH",
                "rule": d.rule_id if d and mismatch else None, "disc_id": d.disc_id if d and mismatch else None}

    def add(self, check_id: str, title: str, rules: tuple[str, ...], left: dict, right: dict, rows: list[dict], skip: str | None = None) -> None:
        if not any(self.ref.rule_active(r, self.stream) for r in rules):
            return                                        # none of its rules apply to this stream
        bad = [r for r in rows if r["result"] == "MISMATCH"]
        discs = sorted({r["disc_id"] for r in bad if r["disc_id"]} | {d.disc_id for r in rules for d in self.by_rule.get(r, [])})
        status = "SKIPPED" if skip else ("MISMATCH" if bad or discs else "MATCH")
        self.checks.append({"check_id": check_id, "title": title, "rules": list(rules), "left": left, "right": right, "status": status,
                            "note": skip, "compared": len(rows), "mismatched": len(bad), "disc_ids": discs, "rows": rows})

    # ------------------------------------------------------------------ CD vs drone
    def cd_vs_drone(self) -> None:
        f = self.f
        L, R = self.side("CD drawing", self.cd_files(), "Equipment drawn"), self.side("Drone survey", self.drone_files(), "Equipment found")
        if not f.cd_items or not f.field_items:
            why = "No CD drawing data was read" if not f.cd_items else "No drone survey data was read"
            for cid, title, rules in (("CD-DRONE-EQUIP", "Antennas and radios present", ("FLD-01", "FLD-07")),
                                      ("CD-DRONE-PIPES", "Mount pipes", ("FLD-02",)), ("CD-DRONE-AZ", "Sector azimuth", ("FLD-04",)),
                                      ("CD-DRONE-RC", "Antenna height (rad center)", ("FLD-03",)), ("CD-DRONE-ROUTE", "Cable route length", ("FLD-06",))):
                self.add(cid, title, rules, L, R, [], skip=why)
            return
        covered = {i.sector for i in f.field_items}
        design = _present_design(f)
        fld = [i for i in f.field_items if i.is_device]
        # devices per sector / position / class
        rows = []
        for sec, pos, cl in sorted({(i.sector, i.position, _cls(i.kind)) for i in design + fld if i.sector in covered}, key=str):
            d_here = [i for i in design if (i.sector, i.position, _cls(i.kind)) == (sec, pos, cl)]
            f_here = [i for i in fld if (i.sector, i.position, _cls(i.kind)) == (sec, pos, cl)]
            noun = {"antenna": "antenna", "radio": "radio"}.get(cl, cl)
            count = lambda items: f"{len(items)} {noun}{'' if len(items) == 1 else 's'}" if items else "none"  # noqa: E731
            rows.append(self.row(f"{_sec(sec)} position {pos}", f"{count(d_here)} drawn", f"{count(f_here)} found", ("FLD-01", "FLD-07"),
                                 sector=sec, position=pos, bad=len(d_here) != len(f_here)))
        self.add("CD-DRONE-EQUIP", "Antennas and radios present", ("FLD-01", "FLD-07"), L, R, rows)
        if self.checks and self.checks[-1]["check_id"] == "CD-DRONE-EQUIP":
            self.checks[-1]["info"] = "Compares what is present and how many at each position. The drone's model names are best guesses, so models are not compared here."
        # mount pipes
        field_pipes = {(i.sector, i.position) for i in f.field_items if i.kind == "pipe"}
        rows = []
        for it in sorted(f.cd_items, key=lambda x: (x.sector, x.position or 0)):
            si = f.sectors.get(it.sector)
            sled_missing = f.is_rooftop and si is not None and si.sled.get("CD") and si.sled.get("FIELD") is False
            if it.kind == "pipe" and it.status == "Existing" and not it.attrs.get("inferred") and it.sector in covered and not sled_missing:
                seen = (it.sector, it.position) in field_pipes
                rows.append(self.row(f"{_sec(it.sector)} position {it.position}", "Existing mount pipe" + (" (spare)" if it.attrs.get("spare") else ""),
                                     "Pipe found" if seen else "No pipe found", ("FLD-02",), sector=it.sector, position=it.position, bad=not seen))
        self.add("CD-DRONE-PIPES", "Mount pipes", ("FLD-02",), self.side("CD drawing", self.cd_files(), "Existing mount pipes drawn"),
                 self.side("Drone survey", self.drone_files(), "Mount pipes found"), rows)
        # roof sleds (rooftop sites only)
        if f.is_rooftop:
            rows = [self.row(_sec(code), "Roof sled shown", "Sled found" if si.sled.get("FIELD") else "No sled found", ("FLD-05",), sector=code,
                             bad=si.sled.get("FIELD") is False) for code, si in sorted(f.sectors.items()) if si.sled.get("CD")]
            self.add("CD-DRONE-SLED", "Roof sleds", ("FLD-05",), self.side("CD drawing", self.cd_files(), "Roof sleds drawn"),
                     self.side("Drone survey", self.drone_files(), "Roof sleds found"), rows)
        # azimuth per sector
        rows = []
        for code, si in sorted(f.sectors.items()):
            fa, ca = si.azimuth.get("FIELD"), si.azimuth.get("CD", si.azimuth.get("RFDS"))
            if fa is not None and ca is not None:
                diff = abs((fa - ca + 180) % 360 - 180)
                rows.append(self.row(_sec(code), f"{ca:g}°", f"{fa:.0f}° ({diff:.0f}° apart, allowed {self.tol_az:g}°)", ("FLD-04",), sector=code,
                                     bad=diff > self.tol_az))
        self.add("CD-DRONE-AZ", "Sector azimuth", ("FLD-04",), self.side("CD drawing", self.cd_files(), "Sector azimuth drawn"),
                 self.side("Drone survey", self.drone_files(), "Sector azimuth measured"), rows)
        # antenna rad center
        rows = []
        for i in (x for x in fld if _cls(x.kind) == "antenna" and x.rad_center_ft is not None):
            m = next((d for d in design + f.rfds_existing if (d.sector, d.position, d.catalog_key) == (i.sector, i.position, i.catalog_key)), None)
            if m and m.rad_center_ft is not None:
                diff = abs(round(i.rad_center_ft) - m.rad_center_ft)
                rows.append(self.row(f"{_sec(i.sector)} position {i.position}", f"{m.rad_center_ft:g} ft", f"{i.rad_center_ft:.0f} ft ({diff:.0f} ft apart, allowed {self.tol_rc:g} ft)",
                                     ("FLD-03",), bad=diff > self.tol_rc))
        self.add("CD-DRONE-RC", "Antenna height (rad center)", ("FLD-03",), self.side("CD drawing", self.cd_files(), "Antenna height drawn"),
                 self.side("Drone survey", self.drone_files(), "Antenna height measured"), rows)
        # cable route
        cdt, ft = f.trunks.get("CD"), f.trunks.get("FIELD")
        rows = []
        if cdt and ft and cdt.horizontal_ft is not None and ft.horizontal_ft is not None:
            diff = abs(cdt.horizontal_ft - ft.horizontal_ft)
            rows.append(self.row("Cabinet to structure", f"{cdt.horizontal_ft:g} ft", f"{ft.horizontal_ft:.1f} ft ({diff:.0f} ft apart, allowed {self.tol_route:g} ft)",
                                 ("FLD-06",), bad=diff > self.tol_route))
        self.add("CD-DRONE-ROUTE", "Cable route length", ("FLD-06",), self.side("CD drawing", self.cd_files(), "Cable schedule length"),
                 self.side("Drone survey", self.drone_files(), "Route measured"), rows,
                 skip=None if rows else "The route length is not on both sources (not measurable on rooftops)")

    # ------------------------------------------------------------------ RFDS vs CD
    def rfds_vs_cd(self) -> None:
        f = self.f
        L, R = self.side("RFDS", self.files("RFDS"), "Final configuration"), self.side("CD drawing", self.cd_files(), "Equipment drawn")
        if not f.rfds_final or not f.cd_items:
            why = "No RFDS data was read" if not f.rfds_final else "No CD drawing data was read"
            for cid, title, rules in (("RFDS-CD-AZ", "Sector azimuth", ("RFC-01",)), ("RFDS-CD-EQUIP", "Equipment and positions", ("RFC-02", "RFC-03", "RFC-04"))):
                self.add(cid, title, rules, L, R, [], skip=why)
            return
        rows = []
        for code, si in sorted(f.sectors.items()):
            a_r, a_c = si.azimuth.get("RFDS"), si.azimuth.get("CD")
            if a_r is not None and a_c is not None:
                rows.append(self.row(_sec(code), f"{a_r:g}°", f"{a_c:g}°", ("RFC-01",), sector=code, bad=abs((a_r - a_c + 180) % 360 - 180) > 0))
        self.add("RFDS-CD-AZ", "Sector azimuth", ("RFC-01",), L, R, rows)
        rf = [i for i in f.rfds_final if i.is_device and i.status != "Remove"]
        cd = [i for i in f.cd_items if i.is_device and i.status != "Remove"]
        rows = []
        for sec in sorted({i.sector for i in rf + cd}):
            for key in sorted({i.catalog_key or i.model_text for i in rf + cd if i.sector == sec}):
                r_p = sorted(i.position for i in rf if i.sector == sec and (i.catalog_key or i.model_text) == key)
                c_p = sorted(i.position for i in cd if i.sector == sec and (i.catalog_key or i.model_text) == key)
                sample = next(i for i in rf + cd if i.sector == sec and (i.catalog_key or i.model_text) == key)
                fmt = lambda p: ("position " + "/".join(map(str, p))) if p else "not present"  # noqa: E731
                rows.append(self.row(f"{_sec(sec)}: {_model(self.ref, sample)}", fmt(r_p), fmt(c_p), ("RFC-02", "RFC-03", "RFC-04"), sector=sec, bad=r_p != c_p))
        self.add("RFDS-CD-EQUIP", "Equipment and positions", ("RFC-02", "RFC-03", "RFC-04"), L, R, rows)

    # ------------------------------------------------------------------ documents, revisions, analyses
    def others(self) -> None:
        f = self.f
        cur = f.rfds_revision
        if cur:
            rows = []
            if f.cd_rfds_reference:
                rows.append(self.row(f"CD {f.cd_revision} drawn from", f"RFDS {cur} (current)", f"RFDS {f.cd_rfds_reference}", ("REV-02",), bad=f.cd_rfds_reference != cur))
            self.add("REV-RFDS-CD", "CD built on the current RFDS", ("REV-02",), self.side("RFDS", self.files("RFDS"), "Current revision"),
                     self.side("CD drawing", self.cd_files(), "RFDS revision named in the notes"), rows,
                     skip=None if rows else "The CD notes do not name an RFDS revision")
            rows = [self.row(a.kind, f"RFDS {cur} (current)", f"RFDS {a.rfds_revision}", ("REV-01",), bad=a.rfds_revision != cur)
                    for a in (f.ma, f.sa) if a and a.rfds_revision]
            self.add("REV-RFDS-MASA", "Structural analyses on the current RFDS", ("REV-01",), self.side("RFDS", self.files("RFDS"), "Current revision"),
                     self.side("MA / SA report", self.files("MA_SA"), "RFDS revision analysed"), rows, skip=None if rows else "No MA/SA report was read")
        rows = []
        for a, rule, lim_rule in ((f.sa, "SA-01", "SA-01"), (f.ma, "MA-01", "MA-01")):
            if a and a.capacity_pct is not None:
                lim = self.ref.consistency_rule(lim_rule)["PARAMS"].get("max_capacity_pct", 100)
                after = a.capacity_after_pct
                # same test as reconcile: a mount that is over capacity but passes once the required modifications are made is not a finding
                bad = a.result == "FAIL" or (a.capacity_pct > lim and (a.kind == "SA" or after is None or after > lim))
                shown = f"{a.capacity_pct:g}% ({a.result})" + (f", {after:g}% after the required modifications" if after is not None and a.kind == "MA" else "")
                rows.append(self.row(a.kind, f"at most {lim:g}%", shown, (rule,), bad=bad))
        self.add("MASA-LIMIT", "Structure and mount capacity", ("SA-01", "MA-01"), self.side("Allowed limit", [], "Maximum capacity"),
                 self.side("MA / SA report", self.files("MA_SA"), "Capacity reported"), rows, skip=None if rows else "No MA/SA report was read")
        if f.ma and f.ma.modifications:
            shown = any("REINFORC" in s.upper() or "MRK" in s.upper() for s in f.site.get("cd_scope_lines", []))
            rows = [self.row(f"{_sec(m['sector'])}: {m['kit_key'] or m['text']} x{m['qty']}", "Required by the mount analysis", "Shown on the CD" if shown else "Not shown on the CD",
                             ("MNT-01",), sector=m["sector"], bad=not shown) for m in f.ma.modifications]
            self.add("MASA-CD-MODS", "Mount modifications drawn", ("MNT-01",), self.side("MA report", self.files("MA_SA"), "Required modifications"),
                     self.side("CD drawing", self.cd_files(), "Reinforcement shown"), rows)
        if f.ma and f.ma.loading and f.rfds_final:
            want = Counter((i.sector, i.position, i.catalog_key) for i in f.rfds_final if i.is_device and i.status != "Remove")
            got = Counter((i.sector, i.position, i.catalog_key) for i in f.ma.loading if i.status != "Remove")
            rows = [self.row(f"{_sec(s)} position {p}", f"{want[(s, p, k)]} on RFDS", f"{got[(s, p, k)]} analysed", ("LOAD-01",), sector=s, position=p,
                             bad=want[(s, p, k)] != got[(s, p, k)]) for s, p, k in sorted(set(want) | set(got), key=str)]
            self.add("MASA-RFDS-LOAD", "Analysed loading matches the RFDS", ("LOAD-01",), self.side("RFDS", self.files("RFDS"), "Final equipment"),
                     self.side("MA report", self.files("MA_SA"), "Equipment analysed"), rows)
        # documents and extraction confidence
        need = self.ref.consistency_rule("DOC-01").get("PARAMS", {}).get("required", {}).get(self.stream, [])
        have = {d.doc_type for d in f.documents if d.status == "CURRENT"}
        have |= {"DRONE"} if any(t.startswith("DRONE") for t in have) else set()
        rows = [self.row(t, "required", "registered" if t in have else "missing", ("DOC-01",), bad=t not in have) for t in need]
        self.add("DOCS-REQUIRED", "Required documents registered", ("DOC-01",), self.side("Requirement", [], "Documents the stream needs"),
                 self.side("Site folder", sorted(d.file_name for d in f.documents if d.status == "CURRENT"), "Documents registered"), rows)
        names = {d.doc_id: d.file_name for d in f.documents}
        per_doc: dict[str, list] = {}
        for x in f.fields:
            per_doc.setdefault(x.doc_id, []).append(x)
        rows = [self.row(names.get(doc_id, doc_id), f"{len(flds)} value(s) read", f"{sum(1 for x in flds if x.needs_review or x.confidence < self.threshold)} below {self.threshold:.0%} confidence",
                         ("EXT-01",), bad=any(x.needs_review or x.confidence < self.threshold for x in flds)) for doc_id, flds in sorted(per_doc.items(), key=lambda kv: names.get(kv[0], ""))]
        self.add("EXT-CONFIDENCE", "Extraction confidence", ("EXT-01",), self.side("Extracted values", [], "Values read from each file"),
                 self.side("Confidence limit", [], f"At least {self.threshold:.0%}"), rows)


def build_comparisons(facts: SiteFacts, ref: ReferenceData, discs: list[Discrepancy], *, stream: str | None = None) -> list[dict]:
    """The stage 3 comparison log for one site (JSON-ready)."""
    lg = _Log(facts, ref, discs, stream or facts.project.get("stream", "BOM"))
    for fn in (lg.cd_vs_drone, lg.rfds_vs_cd, lg.others):
        try:
            fn()
        except Exception:  # noqa: BLE001 - the log is a view; it must never fail a run
            log.exception("comparison log %s failed", fn.__name__, extra={"site_id": facts.site_id})
    return lg.checks
