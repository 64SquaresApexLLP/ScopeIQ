"""Pipeline steps 1-2 - Ingest and Extract: one site folder (+ SiteTracker) -> SiteFacts.

Each extractor is isolated: a failure is recorded (ERROR_LOG + a site warning) and the site continues with
what could be read, so one bad file never blocks the other checks. Missing inputs become DOC-01 findings in
reconcile, never silent defaults.
"""
from __future__ import annotations

from pathlib import Path

from scopeiq.common.context import bind
from scopeiq.common.errors import AppError, ErrorRecorder
from scopeiq.common.logging import get_logger, log_call
from scopeiq.config import get_settings
from scopeiq.domain import SectorInfo, SiteFacts
from scopeiq.extract import bom_rev0, cd, drone, ma_sa, rfds, video
from scopeiq.extract.registry import register_site_folder
from scopeiq.extract.sitetracker import SiteTracker
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)


def _guard(facts: SiteFacts, step: str, fn, *args, **kwargs):
    """Run one extractor; on failure record it and carry on."""
    try:
        return fn(*args, **kwargs)
    except AppError as exc:
        ErrorRecorder.record(exc, where=f"extract.{step}")
        facts.warnings.append(f"{step}: {exc.message}")
    except Exception as exc:  # noqa: BLE001
        ErrorRecorder.record(exc, where=f"extract.{step}")
        facts.warnings.append(f"{step}: unexpected error {type(exc).__name__}: {exc}")
        log.exception("extractor %s failed", step, extra={"site_id": facts.site_id})
    return None


def _merge_sectors(facts: SiteFacts, sectors: dict[str, SectorInfo]) -> None:
    for code, si in sectors.items():
        tgt = facts.sectors.setdefault(code, SectorInfo(code))
        for k, v in si.azimuth.items():
            tgt.azimuth.setdefault(k, v)
        tgt.new_frame = tgt.new_frame or si.new_frame
        for k, v in si.sled.items():
            tgt.sled.setdefault(k, v)


@log_call()
def build_site_facts(site_dir: Path, ref: ReferenceData, *, sitetracker: SiteTracker | None = None,
                     evidence_dir: Path | None = None, site_id: str | None = None, on_ingested=None) -> SiteFacts:
    """`on_ingested(facts)` is called once the documents are registered, before any extractor runs (progress reporting)."""
    st = get_settings()
    site_dir = Path(site_dir)
    site_id = site_id or site_dir.name
    facts = SiteFacts(site_id)
    with bind(site_id=site_id, component="extract"):
        if sitetracker:
            facts.site = sitetracker.site_record(site_id)
            facts.project = sitetracker.project_record(site_id)
            facts.milestones = sitetracker.milestone_records(site_id)
        doc_paths: dict = {}
        facts.documents = register_site_folder(site_dir, site_id, upload_dir=Path(st.path("paths.upload_dir")) / site_id, paths=doc_paths)
        facts.site["doc_paths"] = {k: str(v) for k, v in doc_paths.items()}
        if on_ingested:
            on_ingested(facts)
        path = lambda d: doc_paths.get(d.doc_id) or _abs(site_dir, d.rel_path)  # noqa: E731
        cat = ref.catalog

        # RFDS (governs RF)
        d = facts.doc("RFDS")
        if d:
            r = _guard(facts, "rfds", rfds.extract_rfds, path(d), site_id=site_id, doc_id=d.doc_id, catalog=cat)
            if r:
                facts.rfds_revision, facts.rfds_date, facts.rfds_history = r.revision, r.date, r.history
                facts.rfds_existing, facts.rfds_final = r.existing, r.final
                facts.basebands, facts.dc_load_added_w = r.basebands, r.dc_load_w
                facts.fields += r.fields
                for k, v in (r.site or {}).items():
                    key = k.lower().replace(" (ft)", "_ft").replace(" ", "_")
                    facts.site.setdefault(f"rfds_{key}", v)
                if not facts.site.get("structure_type"):
                    facts.site["structure_type"] = (r.site or {}).get("Structure Type", "")
                for it in r.final:
                    if it.azimuth_deg is not None:
                        facts.sectors.setdefault(it.sector, SectorInfo(it.sector)).azimuth.setdefault("RFDS", it.azimuth_deg)

        # CD - DXF preferred, PDF via OCR
        cds = [x for x in facts.documents if x.doc_type == "CD" and x.status == "CURRENT"]
        top = max((x.revision_rank for x in cds), default=0)          # a newer PDF revision beats an older DXF
        dxf = next((x for x in cds if x.file_format == "DXF" and x.revision_rank == top), None)
        pdf = next((x for x in cds if x.file_format == "PDF" and x.revision_rank == top), None)
        if dxf or pdf:
            rev = (dxf or pdf).revision
            r = _guard(facts, "cd", cd.extract_cd, path(dxf) if dxf else None, path(pdf) if pdf else None, site_id=site_id,
                       doc_ids={"dxf": dxf.doc_id if dxf else None, "pdf": pdf.doc_id if pdf else None}, revision=rev, catalog=cat,
                       ocr_enabled=st.get("engine.ocr_enabled", True), dpi=st.get("engine.ocr_dpi", 600))
            if r:
                facts.cd_items, facts.cd_rfds_reference, facts.cd_revision, facts.cd_method = r.items, r.rfds_reference, r.revision, r.method
                facts.fields += r.fields
                facts.warnings += r.warnings
                _merge_sectors(facts, r.sectors)
                if r.trunk:
                    facts.trunks["CD"] = r.trunk
                facts.site["cd_scope_lines"] = r.scope_lines
                facts.site["cd_jumpers"] = r.jumpers

        # MA / SA
        d = facts.doc("MA_SA")
        if d:
            r = _guard(facts, "ma_sa", ma_sa.extract_ma_sa, path(d), site_id=site_id, doc_id=d.doc_id, catalog=cat)
            if r:
                facts.ma, facts.sa, f = r
                facts.fields += f

        # REV 0 BOM
        d = facts.doc("BOM_REV0")
        if d:
            r = _guard(facts, "bom_rev0", bom_rev0.extract_rev0, path(d), site_id=site_id, doc_id=d.doc_id, catalog=cat)
            if r:
                facts.rev0, facts.site["rev0_meta"], f = r
                facts.fields += f

        # Drone: vendor CSV preferred, else point cloud; video frames as evidence
        design_az = {k: v.azimuth.get("RFDS", v.azimuth.get("CD")) for k, v in facts.sectors.items() if v.azimuth}
        expected = [i for i in facts.rfds_existing] + [i for i in facts.cd_items if i.status in ("Existing", "Remove")]
        vend = next((x for x in facts.documents if x.doc_type == "DRONE_VENDOR" and x.status == "CURRENT"), None)
        cloud = next((x for x in facts.documents if x.doc_type == "DRONE_POINTCLOUD" and x.status == "CURRENT"), None)
        objs, method, src_doc = None, "", None
        if vend:
            objs = _guard(facts, "drone_vendor", drone.read_vendor_csv, path(vend))
            method, src_doc = "VENDOR_CSV", vend
        if not objs and cloud:
            r = _guard(facts, "pointcloud", drone.read_pointcloud, path(cloud), rooftop=facts.is_rooftop)
            if r:
                objs, stats = r
                method, src_doc = "POINTCLOUD", cloud
                facts.site["pointcloud_stats"] = stats
                if stats.get("route_note"):
                    facts.warnings.append(stats["route_note"])
        if objs:
            r = _guard(facts, "field_model", drone.assemble_field_items, objs, site_id=site_id, doc_id=src_doc.doc_id, method=method,
                       catalog=cat, design_azimuths=design_az, rooftop=facts.is_rooftop, expected=expected)
            if r:
                facts.field_items, sectors, trunk, f = r
                facts.field_objects, facts.field_method = objs, method
                facts.fields += f
                _merge_sectors(facts, sectors)
                if trunk:
                    facts.trunks["FIELD"] = trunk
        vid = next((x for x in facts.documents if x.doc_type == "DRONE_VIDEO" and x.status == "CURRENT"), None)
        if vid and evidence_dir:
            facts.frames = _guard(facts, "video", video.sample_frames, path(vid), Path(evidence_dir) / site_id, site_id=site_id,
                                  n_frames=st.get("engine.video_frames_per_site", 24), sector_azimuths=design_az) or []
    log.info("site facts built: rfds=%s cd=%s(%s) field=%s(%d items) ma=%s sa=%s rev0=%d lines, %d warnings", facts.rfds_revision,
             facts.cd_revision, facts.cd_method, facts.field_method, len(facts.field_items), facts.ma.result if facts.ma else None,
             facts.sa.result if facts.sa else None, len(facts.rev0), len(facts.warnings), extra={"site_id": site_id})
    return facts


def _abs(site_dir: Path, rel_path: str) -> Path:
    """'sites/<id>/rfds/x.xlsx' -> <site_dir>/rfds/x.xlsx"""
    parts = Path(rel_path).parts
    return Path(site_dir).joinpath(*parts[2:])
