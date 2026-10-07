"""SiteTracker (tool of record) CSV exports: Site, Project, Milestone, Document (Salesforce-style __c fields)."""
from __future__ import annotations

import csv
from pathlib import Path

from scopeiq.common.logging import get_logger, log_call

log = get_logger(__name__)

SERVICE_LINE_TO_STREAM = {"Site Build BOM Scoping": "BOM", "Site Design Scoping": "DESIGN", "Network Deployment Scoping": "DEPLOYMENT"}


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class SiteTracker:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.sites = _read(self.folder / "Site.csv")
        self.projects = _read(self.folder / "Project.csv")
        self.milestones = _read(self.folder / "Milestone.csv")
        self.documents = _read(self.folder / "Document.csv")
        self._site_by_name = {s["Name"]: s for s in self.sites}
        log.debug("SiteTracker loaded", extra={"sites": len(self.sites), "projects": len(self.projects)})

    def site_ids(self) -> list[str]:
        return sorted(self._site_by_name)

    @log_call()
    def site_record(self, site_id: str) -> dict:
        s = self._site_by_name.get(site_id)
        if not s:
            return {}
        return {
            "site_id": site_id, "sf_id": s["Id"], "site_name": s["Site_Name__c"], "market": s["Market__c"],
            "customer": s["Customer__c"], "address": s["Street__c"], "city": s["City__c"], "state": s["State__c"],
            "zip": s["Zip__c"], "latitude": float(s["Latitude__c"] or 0), "longitude": float(s["Longitude__c"] or 0),
            "structure_type": s["Structure_Type__c"], "height_ft": float(s["Structure_Height_ft__c"] or 0),
            "structure_owner": s["Structure_Owner__c"], "site_status": s["Site_Status__c"], "parent_site_id": None,
        }

    def project_record(self, site_id: str) -> dict:
        s = self._site_by_name.get(site_id)
        if not s:
            return {}
        p = next((p for p in self.projects if p["Site__c"] == s["Id"]), None)
        if not p:
            return {}
        return {
            "project_sf_id": p["Id"], "project_name": p["Name"], "project_type": p["Project_Type__c"],
            "service_line": p["Scoping_Service_Line__c"], "stream": SERVICE_LINE_TO_STREAM.get(p["Scoping_Service_Line__c"], "BOM"),
            "assigned_date": p["Scoping_Assigned_Date__c"], "bom_status": p["BOM_Status__c"], "current_bom_rev": p["Current_BOM_Rev__c"],
            "cx_sp": p["CX_Service_Provider__c"], "scoping_forecast": p["Scoping_Complete_Forecast__c"],
            "scoping_actual": p["Scoping_Complete_Actual__c"] or None, "fba_date": p["FBA_Date__c"] or None,
        }

    def milestone_records(self, site_id: str) -> list[dict]:
        proj = self.project_record(site_id)
        if not proj:
            return []
        rows = [m for m in self.milestones if m["Project__c"] == proj["project_sf_id"]]
        return [{"milestone_sf_id": m["Id"], "name": m["Name"], "forecast": m["Forecast_Date__c"] or None,
                 "actual": m["Actual_Date__c"] or None, "status": m["Status__c"], "seq": int(m["Sequence__c"] or 0)}
                for m in sorted(rows, key=lambda m: int(m["Sequence__c"] or 0))]

    def document_records(self, site_id: str) -> list[dict]:
        proj = self.project_record(site_id)
        return [d for d in self.documents if proj and d["Project__c"] == proj["project_sf_id"]]
