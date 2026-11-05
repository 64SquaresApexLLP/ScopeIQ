"""The BOM as an Excel workbook, written fresh by every run from that run's result."""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill

from scopeiq.bom.engine import BomResult
from scopeiq.domain import SECTOR_NAMES

COLUMNS = ["Site ID", "Market", "Sector", "Technology", "Band", "Equipment Category", "Manufacturer", "Model", "Manufacturer P/N", "Customer P/N",
           "Description", "UOM", "Design Qty", "Spare Qty", "Total Qty", "Supply (CFM/VFM)", "Action", "Source", "Drawing", "BOM Rule", "Revision", "Status"]
WIDTHS = (10, 7, 8, 9, 9, 18, 14, 22, 18, 12, 44, 6, 9, 9, 9, 12, 8, 22, 12, 10, 24, 28)
HEADER = PatternFill("solid", fgColor="1F3864")


def row_values(l) -> list:
    return [l.site_id, l.market, SECTOR_NAMES.get(l.sector, "Site"), l.technology, l.band, l.category, l.manufacturer, l.model, l.mfr_pn, l.customer_pn,
            l.description, l.uom, l.design_qty, l.spare_qty, l.total_qty, l.supply, l.action, l.source, l.drawing, l.rule_id, l.revision, l.status]


def write_bom_workbook(path: Path, site_id: str, result: BomResult) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = site_id
    ws.append(COLUMNS)
    for l in result.lines:
        ws.append(row_values(l))
    iss = wb.create_sheet("Issues")
    iss.append(["Severity", "Code", "Rule", "Sector", "Message"])
    for i in result.issues:
        iss.append([i.severity, i.code, i.rule_id, SECTOR_NAMES.get(i.sector, i.sector or ""), i.message])
    for sheet in (ws, iss):
        for c in sheet[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), HEADER
        sheet.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJKLMNOPQRSTUV", WIDTHS):
        ws.column_dimensions[col].width = w
    for col, w in zip("ABCDE", (10, 24, 10, 10, 110)):
        iss.column_dimensions[col].width = w
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
