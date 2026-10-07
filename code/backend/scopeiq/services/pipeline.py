"""Pipeline orchestration and persistence (guide section 7, steps 1-6; 7-9 are the workflow).

run_site():  Ingest -> Extract -> Reconcile -> Delta -> Generate (AS_DRAWN + FINAL) -> REV 0 check ->
             Estimate -> draft redlines/RFIs -> persist -> files -> advance SITE_SCOPING workflow.

Re-running a site is safe: discrepancy, redline, RFI and EHS ids are stable, so human decisions (status,
reason, assignee) survive; a generated BOM revision still in DRAFT is refreshed in place, while an approved
or locked one is never touched and the run creates the next revision instead.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path

from scopeiq.common.context import bind, current
from scopeiq.common.errors import AppError, ErrorRecorder, NotFound
from scopeiq.common.ids import stable_id
from scopeiq.common.logging import get_logger, log_call
from scopeiq.config import get_settings
from scopeiq.db.repository import Repository, now_iso
from scopeiq.domain import BomLine, SiteFacts
from scopeiq.engine import bom as bom_engine
from scopeiq.engine.design import AS_DRAWN, FINAL, build_model, compute_delta
from scopeiq.engine.drivers import build_drivers, estimate, site_requirements
from scopeiq.engine.facts import build_site_facts
from scopeiq.engine.reconcile import reconcile
from scopeiq.engine.redlines import draft_redlines_and_rfis
from scopeiq.engine.revisions import build_rev1, validate_rev0
from scopeiq.extract.sitetracker import SiteTracker
from scopeiq.outputs.exports import write_bom_xlsx, write_site_package
from scopeiq.outputs.redline_pdf import write_redlined_pdf
from scopeiq.reference.loader import ReferenceData
from scopeiq.workflow.engine import WorkflowEngine

log = get_logger("pipeline")
PIPELINE_STEPS = ["INGEST", "EXTRACT", "RECONCILE"]


class PipelineService:
    def __init__(self, repo: Repository, ref: ReferenceData):
        self.repo, self.ref = repo, ref
        st = get_settings()
        self.sites_dir = st.path("paths.sites_dir")
        self.output_dir = st.path("paths.output_dir")
        self.st_dir = st.path("paths.sitetracker_dir")
        self.wf = WorkflowEngine(ref, repo)
        self._st: SiteTracker | None = None

    @property
    def sitetracker(self) -> SiteTracker | None:
        if self._st is None and (self.st_dir / "Site.csv").exists():
            self._st = SiteTracker(self.st_dir)
        return self._st

    def site_ids(self) -> list[str]:
        return sorted(p.name for p in self.sites_dir.iterdir() if p.is_dir()) if self.sites_dir.exists() else []

    # ------------------------------------------------------------------------------------ run
    @log_call()
    def run_site(self, site_id: str, *, triggered_by: str | None = None) -> dict:
        site_dir = self.sites_dir / site_id
        if not site_dir.is_dir():
            raise NotFound(f"Site folder {site_id} not found", details={"sites_dir": str(self.sites_dir)})
        run_id = f"RUN-{site_id}-{uuid.uuid4().hex[:10]}"
        ctx = current()
        steps: dict[str, str] = {}
        self.repo.insert("CORE.PIPELINE_RUN", [{"RUN_ID": run_id, "SITE_ID": site_id, "STARTED_AT": now_iso(), "STATUS": "RUNNING",
                                               "TRIGGERED_BY": triggered_by or ctx.user_id, "CORRELATION_ID": ctx.correlation_id,
                                               "REFERENCE_VERSIONS": self.ref.versions}])
        with bind(site_id=site_id, component="pipeline"):
            try:
                facts = build_site_facts(site_dir, self.ref, sitetracker=self.sitetracker, evidence_dir=self.output_dir / "evidence")
                steps["INGEST"] = steps["EXTRACT"] = "OK"
                stream = facts.project.get("stream", "BOM")
                discs = reconcile(facts, self.ref, stream=stream)
                steps["RECONCILE"] = "OK"
                as_drawn_m = build_model(facts, self.ref, AS_DRAWN, discs)
                final_m = build_model(facts, self.ref, FINAL, discs)
                delta = compute_delta(final_m)
                steps["DELTA"] = "OK"
                ad_lines, _ = bom_engine.generate_bom(as_drawn_m, self.ref)
                fn_lines, tp = bom_engine.generate_bom(final_m, self.ref)
                rev0_findings = validate_rev0(site_id, facts.rev0, ad_lines, self.ref, stream)
                discs += rev0_findings
                changes = build_rev1(site_id, facts.rev0, ad_lines, fn_lines, discs)
                _apply_reason_codes(fn_lines, changes)
                steps["GENERATE"] = "OK"
                reqs = site_requirements(facts, delta, self.ref)
                drivers = build_drivers(facts, delta, fn_lines, tp, reqs, discs, self.ref)
                est = estimate(facts, delta, fn_lines, tp, reqs, drivers, self.ref)
                steps["ESTIMATE"] = "OK"
                redlines, rfis = draft_redlines_and_rfis(facts, discs, self.ref)
                summary = self._persist(run_id, facts, discs, delta, as_drawn_m, fn_lines, tp, changes, drivers, reqs, est, redlines, rfis)
                summary["files"] = self._write_files(run_id, facts, fn_lines, changes, discs, redlines, rfis, summary)
                self._advance_workflow(site_id)
                self.repo.update("CORE.PIPELINE_RUN", {"FINISHED_AT": now_iso(), "STATUS": "SUCCEEDED" if not facts.warnings else "SUCCEEDED_WITH_WARNINGS",
                                                       "STEPS": steps, "SUMMARY": summary, "WARNINGS": facts.warnings}, {"RUN_ID": run_id})
                log.info("pipeline finished for %s: %s", site_id, json.dumps({k: v for k, v in summary.items() if k != "files"}, default=str))
                return {"run_id": run_id, "site_id": site_id, "status": "SUCCEEDED", "summary": summary, "warnings": facts.warnings}
            except Exception as exc:
                ErrorRecorder.record(exc, where="pipeline.run_site")
                self.repo.update("CORE.PIPELINE_RUN", {"FINISHED_AT": now_iso(), "STATUS": "FAILED", "STEPS": steps,
                                                       "WARNINGS": [str(exc)]}, {"RUN_ID": run_id})
                log.exception("pipeline failed for %s", site_id)
                raise

    def run_all(self, *, triggered_by: str | None = None) -> list[dict]:
        out = []
        for sid in self.site_ids():
            try:
                out.append(self.run_site(sid, triggered_by=triggered_by))
            except AppError as exc:
                out.append({"site_id": sid, "status": "FAILED", "error": exc.to_dict()})
            except Exception as exc:  # noqa: BLE001
                out.append({"site_id": sid, "status": "FAILED", "error": {"message": str(exc)}})
        return out

    # ------------------------------------------------------------------------------------ persist
    def _persist(self, run_id: str, f: SiteFacts, discs, delta, as_drawn_m, fn_lines, tp, changes, drivers, reqs, est, redlines, rfis) -> dict:
        r, sid, ts, user = self.repo, f.site_id, now_iso(), current().user_id
        s, p = f.site, f.project
        existing_site = r.select("CORE.SITE", {"SITE_ID": sid})
        wf_state = existing_site[0]["WORKFLOW_STATE"] if existing_site and existing_site[0].get("WORKFLOW_STATE") else self.wf.initial_state("SITE_SCOPING")
        r.upsert("CORE.SITE", [{
            "SITE_ID": sid, "SF_ID": s.get("sf_id"), "SITE_NAME": s.get("site_name") or s.get("rfds_site_name"), "MARKET": s.get("market"),
            "CUSTOMER": s.get("customer"), "ADDRESS": s.get("address"), "CITY": s.get("city"), "STATE": s.get("state"), "ZIP": s.get("zip"),
            "LATITUDE": s.get("latitude"), "LONGITUDE": s.get("longitude"), "STRUCTURE_TYPE": s.get("structure_type"), "HEIGHT_FT": s.get("height_ft"),
            "STRUCTURE_OWNER": s.get("structure_owner"), "SITE_STATUS": s.get("site_status"), "STREAM": p.get("stream"),
            "PROJECT_SF_ID": p.get("project_sf_id"), "PROJECT_NAME": p.get("project_name"), "PROJECT_TYPE": p.get("project_type"),
            "SERVICE_LINE": p.get("service_line"), "CX_SP": p.get("cx_sp"), "ASSIGNED_DATE": p.get("assigned_date"),
            "SCOPING_FORECAST": p.get("scoping_forecast"), "SCOPING_ACTUAL": p.get("scoping_actual"), "FBA_DATE": p.get("fba_date"),
            "CURRENT_BOM_REV": p.get("current_bom_rev"), "WORKFLOW_STATE": wf_state,
            "ASSIGNED_TO": existing_site[0].get("ASSIGNED_TO") if existing_site else None, "LAST_RUN_ID": run_id, "UPDATED_AT": ts, "UPDATED_BY": user}])
        r.upsert("CORE.MILESTONE", [{"MILESTONE_SF_ID": m["milestone_sf_id"], "SITE_ID": sid, "NAME": m["name"], "SEQ": m["seq"],
                                     "FORECAST": m["forecast"], "ACTUAL": m["actual"], "STATUS": m["status"]} for m in f.milestones])
        r.upsert("CORE.DOCUMENT", [dict({k.upper(): v for k, v in asdict(d).items() if k.upper() in
                                         {"DOC_ID", "SITE_ID", "DOC_TYPE", "FILE_NAME", "REL_PATH", "FILE_FORMAT", "REVISION", "REVISION_RANK", "FILE_HASH",
                                          "SIZE_BYTES", "DOC_DATE", "SOURCE", "STATUS"}}, REGISTERED_AT=ts, REGISTERED_BY=user) for d in f.documents])
        r.insert("CORE.EXTRACTED_FIELD", [{"FIELD_ID": stable_id("FLD", run_id, i), "RUN_ID": run_id, "SITE_ID": sid, "DOC_ID": x.doc_id, "PAGE": x.page,
                                           "FIELD_NAME": x.field_name, "VALUE": {"v": x.value}, "CONFIDENCE": x.confidence, "METHOD": x.method,
                                           "NEEDS_REVIEW": x.needs_review} for i, x in enumerate(f.fields)])
        cfg = [("RFDS_EXISTING", f.rfds_existing), ("RFDS_FINAL", f.rfds_final), ("CD", f.cd_items), ("FIELD", f.field_items),
               ("MA_LOADING", f.ma.loading if f.ma else [])]
        r.insert("CORE.CONFIG_LINE", [{"LINE_ID": stable_id("CFG", run_id, src, i), "RUN_ID": run_id, "SITE_ID": sid, "SOURCE": src, "SECTOR": it.sector,
                                       "POSITION": it.position, "KIND": it.kind, "CATALOG_KEY": it.catalog_key, "MODEL_TEXT": it.model_text,
                                       "STATUS": it.status, "RAD_CENTER_FT": it.rad_center_ft, "AZIMUTH_DEG": it.azimuth_deg, "MECH_TILT": it.mech_tilt,
                                       "BANDS": it.bands, "SOURCE_REF": it.ref.label() if it.ref else None, "CONFIDENCE": it.confidence,
                                       "ATTRS": it.attrs} for src, items in cfg for i, it in enumerate(items)])
        r.insert("CORE.SECTOR_INFO", [{"SITE_ID": sid, "RUN_ID": run_id, "SECTOR": k, "AZ_RFDS": v.azimuth.get("RFDS"), "AZ_CD": v.azimuth.get("CD"),
                                       "AZ_FIELD": v.azimuth.get("FIELD"), "NEW_FRAME": v.new_frame, "SLED_CD": v.sled.get("CD"),
                                       "SLED_FIELD": v.sled.get("FIELD")} for k, v in sorted(f.sectors.items())])
        r.insert("CORE.TRUNK_MEASURE", [{"SITE_ID": sid, "RUN_ID": run_id, "SOURCE": k, "TRUNK_COUNT": t.count, "VERTICAL_FT": t.vertical_ft,
                                         "HORIZONTAL_FT": t.horizontal_ft, "REQUIRED_FT": t.required_ft, "SPECIFIED_FT": t.specified_ft,
                                         "SOURCE_REF": t.ref.label() if t.ref else None} for k, t in f.trunks.items()])
        r.insert("CORE.ANALYSIS_RESULT", [{"SITE_ID": sid, "RUN_ID": run_id, "KIND": a.kind, "REPORT_ID": a.report_id, "REPORT_DATE": a.date,
                                           "RESULT": a.result, "CAPACITY_PCT": a.capacity_pct, "CAPACITY_AFTER_PCT": a.capacity_after_pct,
                                           "RFDS_REVISION": a.rfds_revision, "MODIFICATIONS": a.modifications,
                                           "SOURCE_REF": a.ref.label() if a.ref else None} for a in (f.ma, f.sa) if a])
        r.insert("CORE.REV0_LINE", [{"SITE_ID": sid, "RUN_ID": run_id, "ROW_NUM": l.row, "SECTOR": l.sector, "CATALOG_KEY": l.catalog_key, "MODEL": l.model,
                                     "MFR_PN": l.mfr_pn, "CUSTOMER_PN": l.customer_pn, "DESIGN_QTY": l.design_qty, "SPARE_QTY": l.spare_qty,
                                     "ACTION": l.action, "RULE_ID": l.rule_id, "SOURCE": l.source} for l in f.rev0])
        r.insert("CORE.FIELD_OBJECT", [{"SITE_ID": sid, "RUN_ID": run_id, "OBJECT_ID": o.object_id, "OBJECT_TYPE": o.object_type, "SECTOR": o.sector,
                                        "POSITION": o.position, "BEARING_DEG": o.bearing_deg, "FACING_AZ_DEG": o.facing_az_deg,
                                        "CENTER_HEIGHT_FT": o.center_height_ft, "DIMS_IN": list(o.dims_in) if o.dims_in else None,
                                        "MODEL_GUESS": o.model_guess, "CONFIDENCE": o.confidence, "ROUTE_LENGTH_FT": o.route_length_ft,
                                        "METHOD": o.method} for o in f.field_objects])
        self.repo.delete_where("CORE.EVIDENCE_FRAME", {"SITE_ID": sid})
        r.insert("CORE.EVIDENCE_FRAME", [{"FRAME_ID": stable_id("FRM", sid, fr.frame_index), "RUN_ID": run_id, "SITE_ID": sid, "FRAME_INDEX": fr.frame_index,
                                          "TIME_S": fr.time_s, "BEARING_DEG": fr.bearing_deg, "SECTOR": fr.sector, "SHARPNESS": fr.sharpness,
                                          "PATH": _rel(fr.path, self.output_dir), "SELECTED": fr.selected} for fr in f.frames])
        # discrepancies: keep human decisions across runs
        prev = {d["DISC_ID"]: d for d in r.select("CORE.DISCREPANCY", {"SITE_ID": sid})}
        rows = []
        for d in discs:
            p0 = prev.get(d.disc_id, {})
            rows.append({"DISC_ID": d.disc_id, "SITE_ID": sid, "RUN_ID": run_id, "RULE_ID": d.rule_id, "FAMILY": d.family, "SEVERITY": d.severity,
                         "OUTCOME": d.outcome, "TITLE": d.title, "DESCRIPTION": d.description, "SECTOR": d.sector, "POSITION": d.position,
                         "EXPECTED": {"v": d.expected}, "FOUND": {"v": d.found}, "GOVERNING": d.governing, "SOURCES": d.sources,
                         "TARGET_DOC": d.target_doc, "TARGET_SHEET": d.target_sheet, "BOM_IMPACT": d.bom_impact,
                         "EVIDENCE": [_rel(e, self.output_dir) for e in d.evidence if e], "CONFIDENCE": d.confidence,
                         "STATUS": p0.get("STATUS") or "OPEN", "REASON_CODE": p0.get("REASON_CODE"), "ASSIGNED_TO": p0.get("ASSIGNED_TO"),
                         "FIRST_SEEN_RUN": p0.get("FIRST_SEEN_RUN") or run_id, "LAST_SEEN_RUN": run_id, "CREATED_AT": p0.get("CREATED_AT") or ts,
                         "UPDATED_AT": p0.get("UPDATED_AT") or ts, "UPDATED_BY": p0.get("UPDATED_BY") or user})
        r.upsert("CORE.DISCREPANCY", rows)
        stale = [k for k, v in prev.items() if k not in {d.disc_id for d in discs} and v.get("STATUS") == "OPEN"]
        for k in stale:      # no longer reproduced (e.g. corrected document uploaded): close automatically, audited
            r.update("CORE.DISCREPANCY", {"STATUS": "RESOLVED", "REASON_CODE": "RC-AE-REVISED", "UPDATED_AT": ts, "UPDATED_BY": "system"}, {"DISC_ID": k})
        r.insert("CORE.EQUIPMENT_DELTA", [{"SITE_ID": sid, "RUN_ID": run_id, "SEQ": i, "SECTOR": d.sector, "POSITION": d.position, "KIND": d.kind,
                                           "CATALOG_KEY": d.catalog_key, "ACTION": d.action, "FROM_POSITION": d.from_position,
                                           "RAD_CENTER_FT": d.rad_center_ft, "BASIS": d.basis, "SOURCE_REF": d.ref.label() if d.ref else None}
                                          for i, d in enumerate(delta)])
        bom_info = self._persist_bom(run_id, f, fn_lines, tp, changes)
        r.insert("CORE.DRIVER_LINE", [{"LINE_ID": stable_id("DRV", run_id, i), "RUN_ID": run_id, "SITE_ID": sid, "DRIVER_CODE": d.driver_code,
                                       "DESCRIPTION": d.description, "SECTOR": d.sector, "QTY": d.qty, "UOM": d.uom, "UNIT_RATE": d.unit_rate,
                                       "AMOUNT": d.amount, "BASIS": d.basis} for i, d in enumerate(drivers)])
        r.upsert("CORE.SITE_REQUIREMENT", [{"SITE_ID": sid, "RUN_ID": run_id, "RULE_ID": reqs["rule_id"], "ACCESS_METHOD": reqs["access_method"],
                                            "CRANE_DAYS": reqs["crane_days"], "MANLIFT_DAYS": reqs["manlift_days"], "RIGGING_CLASS": reqs["rigging_class"],
                                            "HOLD": reqs["hold"], "INPUTS": reqs["inputs"]}])
        r.upsert("CORE.ESTIMATE", [{"SITE_ID": sid, "RUN_ID": run_id, "CYCLE_DAYS": est["cycle_days"], "SERVICES_USD": est["services_usd"],
                                    "MATERIAL_USD": est["material_usd"], "TOTAL_USD": est["total_usd"], "DETAIL": est}])
        prev_alerts = {a["ALERT_ID"]: a for a in r.select("CORE.EHS_ALERT", {"SITE_ID": sid})}
        r.upsert("CORE.EHS_ALERT", [{"ALERT_ID": (aid := stable_id("EHS", sid, a["rule_id"])), "SITE_ID": sid, "RULE_ID": a["rule_id"],
                                     "SEVERITY": a["severity"], "ALERT_TEXT": a["text"], "STATUS": prev_alerts.get(aid, {}).get("STATUS") or "OPEN",
                                     "CREATED_AT": prev_alerts.get(aid, {}).get("CREATED_AT") or ts, "UPDATED_AT": ts, "UPDATED_BY": user}
                                    for a in reqs["ehs_alerts"]])
        prev_rl = {x["REDLINE_ID"]: x for x in r.select("CORE.REDLINE", {"SITE_ID": sid})}
        r.upsert("CORE.REDLINE", [{"REDLINE_ID": x.redline_id, "SITE_ID": sid, "DISC_ID": x.disc_id, "DOC_TYPE": x.doc_type, "DOC_REVISION": x.doc_revision,
                                   "SHEET": x.sheet, "MARKUP": x.markup, "CHANGE_FROM": x.change_from, "CHANGE_TO": x.change_to,
                                   "STATUS": prev_rl.get(x.redline_id, {}).get("STATUS") or "DRAFT", "PDF_PATH": prev_rl.get(x.redline_id, {}).get("PDF_PATH"),
                                   "CREATED_AT": prev_rl.get(x.redline_id, {}).get("CREATED_AT") or ts, "UPDATED_AT": ts, "UPDATED_BY": user} for x in redlines])
        for x in redlines:
            x.status = prev_rl.get(x.redline_id, {}).get("STATUS") or "DRAFT"
        prev_rfi = {x["RFI_ID"]: x for x in r.select("CORE.RFI", {"SITE_ID": sid})}
        r.upsert("CORE.RFI", [{"RFI_ID": x.rfi_id, "SITE_ID": sid, "TO_PARTY": x.to_party, "SUBJECT": x.subject, "QUESTION": x.question,
                               "PROPOSED_ANSWER": x.proposed_answer, "ANSWER": prev_rfi.get(x.rfi_id, {}).get("ANSWER"), "DISC_IDS": x.disc_ids,
                               "STATUS": prev_rfi.get(x.rfi_id, {}).get("STATUS") or "DRAFT", "CREATED_AT": prev_rfi.get(x.rfi_id, {}).get("CREATED_AT") or ts,
                               "UPDATED_AT": ts, "UPDATED_BY": user} for x in rfis])
        sev = {}
        for d in discs:
            sev[d.outcome] = sev.get(d.outcome, 0) + 1
        return {"discrepancies": len(discs), "by_outcome": sev, "redlines": len(redlines), "rfis": len(rfis), "bom": bom_info,
                "trunk": {k: tp.get(k) for k in ("count", "length_ft", "required_ft", "horizontal_basis", "held")},
                "estimate": est, "requirements": {k: reqs[k] for k in ("rule_id", "access_method", "crane_days", "rigging_class", "hold")},
                "field_method": f.field_method, "cd_method": f.cd_method, "warnings": len(f.warnings)}

    def _persist_bom(self, run_id: str, f: SiteFacts, lines: list[BomLine], tp, changes: list[dict]) -> dict:
        r, sid, ts, user = self.repo, f.site_id, now_iso(), current().user_id
        revs = sorted(r.select("CORE.BOM_REVISION", {"SITE_ID": sid}), key=lambda x: x["REV_NO"])
        rev0_id = f"{sid}-REV0"
        if f.rev0 and not any(x["BOM_REV_ID"] == rev0_id for x in revs):
            r.insert("CORE.BOM_REVISION", [{"BOM_REV_ID": rev0_id, "SITE_ID": sid, "REV_NO": 0, "REV_LABEL": "REV 0", "KIND": "TOOL_REV0",
                                            "STATUS": "RECEIVED", "LOCKED": True, "RUN_ID": run_id, "CREATED_AT": ts, "CREATED_BY": "ericsson-tool",
                                            "NOTES": "Preliminary BOM from the Ericsson tool (read-only)"}])
            r.insert("CORE.BOM_LINE", [{"LINE_ID": stable_id("BL", rev0_id, l.row), "BOM_REV_ID": rev0_id, "SITE_ID": sid, "SECTOR": l.sector,
                                        "CATALOG_KEY": l.catalog_key or l.model, "DESIGN_QTY": l.design_qty, "SPARE_QTY": l.spare_qty,
                                        "TOTAL_QTY": l.design_qty + l.spare_qty, "ACTION": "Remove" if l.action.lower().startswith("rem") else "Install",
                                        "RULE_ID": l.rule_id, "SOURCE": l.source, "TRACE": {"row": l.row, "mfr_pn": l.mfr_pn}} for l in f.rev0])
        gen = [x for x in revs if x["REV_NO"] >= 1]
        latest = gen[-1] if gen else None
        if latest and latest["STATUS"] == "DRAFT" and not latest.get("LOCKED"):
            rev_id, rev_no = latest["BOM_REV_ID"], latest["REV_NO"]
            r.delete_where("CORE.BOM_LINE", {"BOM_REV_ID": rev_id})
            r.delete_where("CORE.BOM_CHANGE", {"TO_REV_ID": rev_id})
            r.update("CORE.BOM_REVISION", {"RUN_ID": run_id, "TRUNK_PLAN": dict(tp), "CREATED_AT": ts}, {"BOM_REV_ID": rev_id})
        else:
            rev_no = (latest["REV_NO"] + 1) if latest else 1
            rev_id = f"{sid}-REV{rev_no}"
            r.insert("CORE.BOM_REVISION", [{"BOM_REV_ID": rev_id, "SITE_ID": sid, "REV_NO": rev_no, "REV_LABEL": f"REV {rev_no}", "KIND": "GENERATED",
                                            "STATUS": "DRAFT", "LOCKED": False, "RUN_ID": run_id, "PARENT_REV_ID": latest["BOM_REV_ID"] if latest else rev0_id,
                                            "TRUNK_PLAN": dict(tp), "CREATED_AT": ts, "CREATED_BY": user,
                                            "NOTES": "Generated by kitting rules on the corrected site (RFDS + field + MA)"}])
        r.insert("CORE.BOM_LINE", [{"LINE_ID": stable_id("BL", rev_id, i), "BOM_REV_ID": rev_id, "SITE_ID": sid, "SECTOR": l.sector, "CATALOG_KEY": l.catalog_key,
                                    "DESIGN_QTY": l.design_qty, "SPARE_QTY": l.spare_qty, "TOTAL_QTY": l.total_qty, "ACTION": l.action, "RULE_ID": l.rule_id,
                                    "SOURCE": l.source, "PARENT_KEY": l.parent_key, "REASON_CODE": l.reason_code, "TRACE": l.trace} for i, l in enumerate(lines)])
        r.insert("CORE.BOM_CHANGE", [{"CHANGE_ID": stable_id("CHG", rev_id, i), "SITE_ID": sid, "FROM_REV_ID": rev0_id, "TO_REV_ID": rev_id,
                                      "SECTOR": c["sector"], "CATALOG_KEY": c["part"], "ACTION": c["action"], "FROM_QTY": c["rev0_qty"], "TO_QTY": c["rev1_qty"],
                                      "DELTA": c["delta"], "REASONS": c["reasons"]} for i, c in enumerate(changes)])
        totals = {"lines": len(lines), "install_qty": sum(l.total_qty for l in lines if l.action == "Install"),
                  "remove_qty": sum(l.total_qty for l in lines if l.action == "Remove"), "changes_vs_rev0": len(changes)}
        r.update("CORE.BOM_REVISION", {"TOTALS": totals}, {"BOM_REV_ID": rev_id})
        return {"rev_id": rev_id, "rev_label": f"REV {rev_no}", **totals}

    # ------------------------------------------------------------------------------------ files
    def _write_files(self, run_id, f: SiteFacts, fn_lines, changes, discs, redlines, rfis, summary) -> dict:
        out = self.output_dir / "sites" / f.site_id
        files = {}
        rev_label = summary["bom"]["rev_label"]
        files["bom_xlsx"] = str(write_bom_xlsx(out / f"{f.site_id}_BOM_{rev_label.replace(' ', '')}.xlsx", f.site_id, f.site.get("market") or "DFW",
                                               fn_lines, self.ref, rev_label, "Draft", changes))
        cd_pdf = next((d for d in f.documents if d.doc_type == "CD" and d.file_format == "PDF" and d.status == "CURRENT"), None)
        if cd_pdf:
            pdf = write_redlined_pdf(Path(f.site["doc_paths"].get(cd_pdf.doc_id) or self.sites_dir / f.site_id / Path(*Path(cd_pdf.rel_path).parts[2:])),
                                     out / "redlines" / f"{f.site_id}_CD_{(f.cd_revision or 'REV').replace(' ', '')}_REDLINED.pdf",
                                     redlines, site_id=f.site_id)
            if pdf:
                files["redlined_cd_pdf"] = str(pdf)
                for x in redlines:
                    if x.doc_type == "CD":
                        self.repo.update("CORE.REDLINE", {"PDF_PATH": _rel(str(pdf), self.output_dir)}, {"REDLINE_ID": x.redline_id})
        files.update(write_site_package(out / "redlines", f.site_id, discs, redlines, rfis))
        return {k: _rel(v, self.output_dir) for k, v in files.items()}

    # ------------------------------------------------------------------------------------ workflow
    def _advance_workflow(self, site_id: str) -> None:
        state = self.repo.get("CORE.SITE", SITE_ID=site_id)["WORKFLOW_STATE"]
        path = {"ASSIGNED": ["INGEST", "EXTRACT", "RECONCILE", "GENERATE"], "DOCS_INGESTED": ["EXTRACT", "RECONCILE", "GENERATE"],
                "EXTRACTED": ["RECONCILE", "GENERATE"], "IN_RECONCILIATION": ["GENERATE"], "REWORK": ["GENERATE"]}.get(state, [])
        with bind(user_id="system", role="SYSTEM"):
            for action in path:
                self.wf.transition("SITE_SCOPING", site_id, action, site_id=site_id)


def _rel(path: str, base: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return str(path)


def _apply_reason_codes(lines: list[BomLine], changes: list[dict]) -> None:
    """Lines that changed vs REV 0 carry the change's (first) reason code; untouched lines stay RC-RULE-APPLIED."""
    reason = {(c["sector"], c["part"], c["action"]): c["reasons"][0]["reason_code"] for c in changes if c["reasons"]}
    for l in lines:
        rc = reason.get((l.sector, l.catalog_key, l.action))
        if rc:
            l.reason_code = rc
