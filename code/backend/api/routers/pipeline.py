"""Pipeline: start a run (in the background, or wait for it), follow its steps, and read what each step produced.

POST /pipeline/sites/{id}/start    starts a run and returns its run_id at once; poll GET /pipeline/runs/{run_id}
POST /pipeline/sites/{id}/run      runs to completion before answering (scripts, tests)
GET  /pipeline/runs/{run_id}       the run with its steps: status, timing, counts, one-line message per step
GET  /pipeline/runs/{run_id}/steps/{key}   the rows the step produced (documents, findings, BOM, redlines ...)
In Snowflake the same service runs as a Snowpark procedure from a task."""
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.deps import check_site_scope, current_user, pipeline, ref as reference, repo, require, site_scope
from api.schemas import RunIn
from scopeiq.common.errors import NotFound
from scopeiq.config import get_settings
from scopeiq.domain import FieldObject
from scopeiq.extract.drone import identify_object
from scopeiq.services.pipeline import APPLY_PREFIX, STEP_DEFS

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
STEP_KEYS = [k for k, _ in STEP_DEFS]


@router.post("/sites/{site_id}/start")
def start_site(site_id: str, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    return pipeline().start_site(site_id, triggered_by=user["sub"])


@router.post("/sites/{site_id}/run")
def run_site(site_id: str, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    return pipeline().run_site(site_id, triggered_by=user["sub"])


@router.post("/run")
def run_many(body: RunIn, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    svc = pipeline()
    if not body.site_ids:
        return svc.run_all(triggered_by=user["sub"])
    out = []
    for sid in body.site_ids:
        try:
            out.append(svc.run_site(sid, triggered_by=user["sub"]))
        except Exception as exc:  # noqa: BLE001 - report per site, keep going
            out.append({"site_id": sid, "status": "FAILED", "error": getattr(exc, "to_dict", lambda: {"message": str(exc)})()})
    return out


@router.get("/runs")
def runs(site_id: str | None = None, limit: int = 50, user: dict = Depends(current_user)):
    rows = repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id} if site_id else None, order_by="STARTED_AT DESC", limit=limit)
    scope = site_scope(user)
    if scope:
        ok = {s["SITE_ID"] for s in repo().select("CORE.SITE", scope)}
        rows = [r for r in rows if r["SITE_ID"] in ok]
    return rows


def _run(run_id: str, user: dict) -> dict:
    rows = repo().select("CORE.PIPELINE_RUN", {"RUN_ID": run_id}, limit=1)
    if not rows:
        raise NotFound(f"Run {run_id} not found")
    check_site_scope(user, rows[0]["SITE_ID"])
    return rows[0]


@router.get("/sites/{site_id}/latest")
def latest_run(site_id: str, user: dict = Depends(current_user)):
    """The newest pipeline run of a site (running or finished), or null when it has never run."""
    check_site_scope(user, site_id)
    rows = repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id}, order_by="STARTED_AT DESC", limit=30)
    return next((r for r in rows if r["RUN_ID"].startswith("RUN-")), None)


# ---- implement changes: approved redlines -> next CD revision
@router.post("/sites/{site_id}/apply")
def apply_changes(site_id: str, user: dict = Depends(require("REVIEWER", "AE_ENGINEER", "SCOPER"))):
    """Build the next CD revision from the approved redlines (background job; poll GET /pipeline/runs/{run_id})."""
    check_site_scope(user, site_id)
    return pipeline().start_apply(site_id, triggered_by=user["sub"])


@router.get("/sites/{site_id}/revision")
def latest_revision(site_id: str, user: dict = Depends(current_user)):
    """The newest implemented revision (files and the per-redline applied / not applied log), the running job, or null."""
    check_site_scope(user, site_id)
    rows = repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id}, order_by="STARTED_AT DESC", limit=30)
    jobs = [r for r in rows if r["RUN_ID"].startswith(APPLY_PREFIX)]
    done = pipeline().latest_revision(site_id)
    return {"job": jobs[0] if jobs else None, "revision": done}


@router.get("/runs/{run_id}/file/{kind}")
def run_file(run_id: str, kind: str, user: dict = Depends(current_user)):
    """Authenticated download of a file a run wrote (revised drawing, change log)."""
    run = _run(run_id, user)
    rel = ((run.get("SUMMARY") or {}).get("files") or {}).get(kind)
    base = Path(get_settings().path("paths.output_dir")).resolve()
    path = (base / rel).resolve() if rel else None
    if not path or base not in path.parents or not path.is_file():
        raise NotFound(f"File {kind} is not available for run {run_id}")
    return FileResponse(path, filename=path.name)


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: dict = Depends(current_user)):
    return _run(run_id, user)


@router.get("/runs/{run_id}/steps/{key}")
def step_detail(run_id: str, key: str, user: dict = Depends(current_user)):
    """What a step produced, read from the tables the run wrote (so it matches the rest of the app)."""
    key = key.upper()
    if key not in STEP_KEYS:
        raise NotFound(f"Unknown step {key}", details={"steps": STEP_KEYS})
    run = _run(run_id, user)
    r, sid = repo(), run["SITE_ID"]
    by_run = {"SITE_ID": sid, "RUN_ID": run_id}
    if key == "INGEST":
        docs = r.select("CORE.DOCUMENT", {"SITE_ID": sid}, order_by="DOC_TYPE, REVISION_RANK DESC")
        formats = sorted({d.get("FILE_FORMAT") for d in docs if d.get("FILE_FORMAT")})
        current_docs = [d for d in docs if d.get("STATUS") == "CURRENT"]
        superseded_docs = [d for d in docs if d.get("STATUS") == "SUPERSEDED"]
        return {
            "documents": docs,
            "total": len(docs),
            "formats": formats,
            "current_count": len(current_docs),
            "superseded_count": len(superseded_docs),
        }
    if key == "EXTRACT":
        from pathlib import Path as _Path
        from scopeiq.config import get_settings as _get_settings

        fields = r.select("CORE.EXTRACTED_FIELD", by_run)
        fields.sort(key=lambda f: (not f.get("NEEDS_REVIEW"), f.get("CONFIDENCE") or 0))
        cfg_lines = r.select("CORE.CONFIG_LINE", by_run, order_by="SOURCE, SECTOR, POSITION")

        # Dynamic documents for format check
        site_docs = r.select("CORE.DOCUMENT", {"SITE_ID": sid}, order_by="DOC_TYPE, REVISION_RANK DESC")
        drone_docs = [d for d in site_docs if d.get("DOC_TYPE", "").startswith("DRONE")]
        cd_docs = [d for d in site_docs if d.get("DOC_TYPE") == "CD"]

        # --- Real data format check: inspect actual files on disk dynamically ---
        _st = _get_settings()
        _sites_dir = _st.path("paths.sites_dir")
        _site_dir = _Path(_sites_dir) / sid

        detected_drone_formats: list = []
        _seen_fmt: set = set()
        for _doc in drone_docs:
            _fmt = (_doc.get("FILE_FORMAT") or "").upper()
            _rel_path = _doc.get("REL_PATH") or ""
            _file_path = None
            if _rel_path:
                _parts = _Path(_rel_path).parts
                _candidate = _site_dir / _Path(*_parts[2:]) if len(_parts) > 2 else _site_dir / _rel_path
                if _candidate.exists():
                    _file_path = _candidate
            if _fmt and _fmt not in _seen_fmt:
                _seen_fmt.add(_fmt)
                _size_kb = round(_file_path.stat().st_size / 1024, 1) if _file_path and _file_path.exists() else None
                detected_drone_formats.append({
                    "format": _fmt,
                    "doc_type": _doc.get("DOC_TYPE", ""),
                    "file_name": _doc.get("FILE_NAME", ""),
                    "size_kb": _size_kb,
                    "on_disk": bool(_file_path and _file_path.exists()),
                })

        # Drone document pointers
        drone_pointcloud = next((d for d in drone_docs if d.get("DOC_TYPE") == "DRONE_POINTCLOUD"), None)
        drone_vendor = next((d for d in drone_docs if d.get("DOC_TYPE") == "DRONE_VENDOR"), None)

        # Drone format list (for compatibility)
        drone_formats = sorted({d.get("FILE_FORMAT") for d in drone_docs if d.get("FILE_FORMAT")})

        # Field items and identified objects from CORE.FIELD_OBJECT (real LAZ extraction output)
        field_items = [c for c in cfg_lines if c.get("SOURCE") == "FIELD"]
        field_objs = r.select("CORE.FIELD_OBJECT", {"SITE_ID": sid, "RUN_ID": run_id})
        field_trunks = r.select("CORE.TRUNK_MEASURE", {"SITE_ID": sid, "RUN_ID": run_id, "SOURCE": "FIELD"})

        # Build structured identified-objects list from FIELD_OBJECT table (real LAZ output, dynamic)
        identified_objects: list = []
        _catalog = reference().catalog
        for _obj in field_objs:
            _dims = _obj.get("DIMS_IN")
            _match = identify_object(FieldObject(
                _obj.get("OBJECT_ID"), _obj.get("OBJECT_TYPE"), _obj.get("SECTOR"), _obj.get("BEARING_DEG"), _obj.get("FACING_AZ_DEG"),
                _obj.get("CENTER_HEIGHT_FT"), tuple(_dims) if _dims else None, _obj.get("MODEL_GUESS") or "", _obj.get("CONFIDENCE") or 0.0,
                _obj.get("ROUTE_LENGTH_FT"), _obj.get("METHOD") or "", _obj.get("POSITION")), _catalog)
            identified_objects.append({
                "catalog": _match,
                "dims_in": _dims,
                "object_id": _obj.get("OBJECT_ID"),
                "object_type": _obj.get("OBJECT_TYPE"),
                "sector": _obj.get("SECTOR"),
                "position": _obj.get("POSITION"),
                "center_height_ft": _obj.get("CENTER_HEIGHT_FT"),
                "facing_az_deg": _obj.get("FACING_AZ_DEG"),
                "bearing_deg": _obj.get("BEARING_DEG"),
                "dims_in": _obj.get("DIMS_IN"),
                "model_guess": _obj.get("MODEL_GUESS") or "",
                "confidence": _obj.get("CONFIDENCE"),
                "route_length_ft": _obj.get("ROUTE_LENGTH_FT"),
                "method": _obj.get("METHOD"),
            })

        # Summary by object type
        obj_type_counts: dict = {}
        for _obj in identified_objects:
            _t = _obj.get("object_type") or "Unknown"
            obj_type_counts[_t] = obj_type_counts.get(_t, 0) + 1

        drone_extraction = {
            "formats": drone_formats,
            "detected_formats": detected_drone_formats,
            "documents": drone_docs,
            "method": "POINTCLOUD (LiDAR 3D)" if drone_pointcloud else ("VENDOR_CSV" if drone_vendor else "FIELD_SURVEY"),
            "items_count": len(field_items),
            "objects_count": len(identified_objects) or len(field_items),
            "trunk": field_trunks[0] if field_trunks else None,
            "identified_objects": identified_objects,
            "obj_type_counts": obj_type_counts,
            "items": field_items,
        }

        # CD drawings tools and format inspection
        cd_formats = sorted({d.get("FILE_FORMAT") for d in cd_docs if d.get("FILE_FORMAT")})
        cd_dxf = next((d for d in cd_docs if d.get("FILE_FORMAT") == "DXF"), None)
        cd_pdf = next((d for d in cd_docs if d.get("FILE_FORMAT") == "PDF"), None)
        _cd_current = [d for d in cd_docs if (d.get("STATUS") or "CURRENT") == "CURRENT"]   # the revision actually read

        # Real per-file format check for the drawings (every CD file registered for the site, with its status)
        detected_cd_formats: list = []
        for _doc in cd_docs:
            _rel_path = _doc.get("REL_PATH") or ""
            _file_path = None
            if _rel_path:
                _parts = _Path(_rel_path).parts
                _candidate = _site_dir / _Path(*_parts[2:]) if len(_parts) > 2 else _site_dir / _rel_path
                if _candidate.exists():
                    _file_path = _candidate
            detected_cd_formats.append({
                "format": (_doc.get("FILE_FORMAT") or "").upper(),
                "doc_type": _doc.get("DOC_TYPE", ""),
                "file_name": _doc.get("FILE_NAME", ""),
                "revision": _doc.get("REVISION") or "",
                "status": _doc.get("STATUS") or "",
                "size_kb": round(_file_path.stat().st_size / 1024, 1) if _file_path else None,
                "on_disk": bool(_file_path),
            })

        cd_tools = []
        if cd_dxf:
            cd_tools.append({
                "tool": "ezdxf",
                "format": ".dxf (CAD Model Space)",
                "description": "Reads CAD block entities (ANT_PANEL, AAU, RRU, PIPE, SLED) and vector tables with 99% precision."
            })
        if cd_pdf:
            cd_tools.append({
                "tool": "PyMuPDF + OpenCV + Tesseract OCR",
                "format": ".pdf (Drawing Sheets)",
                "description": "Renders vector sheets, eliminates schedule gridlines via OpenCV morphology, and runs Tesseract OCR."
            })

        cd_items = [c for c in cfg_lines if c.get("SOURCE") == "CD"]
        cd_trunks = r.select("CORE.TRUNK_MEASURE", {"SITE_ID": sid, "RUN_ID": run_id, "SOURCE": "CD"})
        cd_rev = (cd_docs[0].get("REVISION") if cd_docs else None) or "REV 1"

        cd_extraction = {
            "formats": cd_formats,
            "detected_formats": detected_cd_formats,
            "tools": cd_tools,
            "documents": cd_docs,
            "method": ("DXF (CAD Model Blocks)" if any(d.get("FILE_FORMAT") == "DXF" for d in _cd_current)
                       else "PDF (Tesseract OCR)"),
            "revision": cd_rev,
            "items_count": len(cd_items),
            "trunk": cd_trunks[0] if cd_trunks else None,
            "items": cd_items,
            "issues": [str(w)[4:].strip() for w in (run.get("WARNINGS") or []) if str(w).lower().startswith("cd:")],   # why the drawing could not be read
        }

        # Query structured comparison records stored directly in SQLite CORE.EXTRACTED_COMPARISON_RECORD
        cmp_records = r.select("CORE.EXTRACTED_COMPARISON_RECORD", by_run, order_by="COMPARISON_CATEGORY, SOURCE, SECTOR, POSITION")
        by_cat = {}
        for cr in cmp_records:
            cat = cr.get("COMPARISON_CATEGORY", "OTHER")
            by_cat[cat] = by_cat.get(cat, 0) + 1
        by_src = {}
        for cr in cmp_records:
            src = cr.get("SOURCE", "OTHER")
            by_src[src] = by_src.get(src, 0) + 1

        return {
            "total": len(fields),
            "needs_review": sum(1 for f in fields if f.get("NEEDS_REVIEW")),
            "fields": fields[:150],
            "config_lines": cfg_lines[:300],
            "drone_extraction": drone_extraction,
            "cd_extraction": cd_extraction,
            "comparison_records": cmp_records,
            "comparison_summary": {
                "total": len(cmp_records),
                "by_category": by_cat,
                "by_source": by_src,
                "db_table": "CORE.EXTRACTED_COMPARISON_RECORD",
                "database": "SQLite (code/output/scopeiq_local.db)",
            },
        }
    if key == "RECONCILE":
        found = r.select("CORE.DISCREPANCY", by_run, order_by="SEVERITY, RULE_ID")
        return {"discrepancies": [d for d in found if d.get("FAMILY") != "REV0_BOM"],    # REV 0 checks belong to the BOM stage
                "comparisons": (run.get("SUMMARY") or {}).get("comparisons", [])}
    if key == "DELTA":
        return {"delta": r.select("CORE.EQUIPMENT_DELTA", by_run, order_by="SEQ")}
    if key == "GENERATE":
        revs = r.select("CORE.BOM_REVISION", {"SITE_ID": sid, "RUN_ID": run_id})
        rev = max(revs, key=lambda x: x["REV_NO"]) if revs else None
        return {"revision": rev, "changes": r.select("CORE.BOM_CHANGE", {"TO_REV_ID": rev["BOM_REV_ID"]}) if rev else [],
                "lines": len(r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev["BOM_REV_ID"]})) if rev else 0}
    if key == "ESTIMATE":
        est = r.select("CORE.ESTIMATE", by_run)
        return {"estimate": est[0] if est else None, "drivers": r.select("CORE.DRIVER_LINE", by_run),
                "requirements": (r.select("CORE.SITE_REQUIREMENT", by_run) or [None])[0]}
    if key == "REDLINES":
        summary = run.get("SUMMARY") or {}
        return {"redlines": r.select("CORE.REDLINE", {"SITE_ID": sid}, order_by="SHEET"), "rfis": r.select("CORE.RFI", {"SITE_ID": sid}),
                "decision": summary.get("redline_decision"), "files": summary.get("files", {})}
    return {"files": (run.get("SUMMARY") or {}).get("files", {})}


@router.get("/sites")
def available_sites(user: dict = Depends(current_user)):
    return pipeline().site_ids()


@router.get("/runs/{run_id}/comparison-records")
def run_comparison_records(run_id: str, category: str | None = None, source: str | None = None, user: dict = Depends(current_user)):
    """Fetch structured comparison records stored in SQLite CORE.EXTRACTED_COMPARISON_RECORD."""
    run = _run(run_id, user)
    r, sid = repo(), run["SITE_ID"]
    where = {"SITE_ID": sid, "RUN_ID": run_id}
    if category:
        where["COMPARISON_CATEGORY"] = category.upper()
    if source:
        where["SOURCE"] = source.upper()
    records = r.select("CORE.EXTRACTED_COMPARISON_RECORD", where, order_by="COMPARISON_CATEGORY, SOURCE, SECTOR, POSITION")
    return {
        "run_id": run_id,
        "site_id": sid,
        "total": len(records),
        "records": records,
        "db_table": "CORE.EXTRACTED_COMPARISON_RECORD",
        "database": "SQLite (output/scopeiq_local.db)",
    }
