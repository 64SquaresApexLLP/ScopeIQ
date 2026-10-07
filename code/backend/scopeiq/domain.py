"""Domain objects shared by extractors and engines. They map 1:1 to the core tables in Section 10 of the team
guide (DOCUMENT, EXTRACTED_FIELD, CONFIG_LINE, EQUIPMENT_DELTA, DISCREPANCY, BOM_LINE, DRIVER_LINE ...)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SECTOR_NAMES = {"A": "Alpha", "B": "Beta", "C": "Gamma", "D": "Delta"}
SECTOR_CODES = {v.upper(): k for k, v in SECTOR_NAMES.items()} | {k: k for k in SECTOR_NAMES}


def sector_code(text: Any) -> str | None:
    t = str(text or "").strip().upper()
    return SECTOR_CODES.get(t) or SECTOR_CODES.get(t[:1]) if t else None


@dataclass
class SourceRef:
    doc_id: str
    doc_type: str
    revision: str = ""
    page: str = ""          # page number, sheet (A-3) or row reference
    detail: str = ""

    def label(self) -> str:
        parts = [self.doc_type, self.revision]
        if self.page:
            parts.append(self.page)
        if self.detail:
            parts.append(self.detail)
        return " ".join(p for p in parts if p)


@dataclass
class Document:
    doc_id: str
    site_id: str
    doc_type: str            # RFDS | CD | MA_SA | BOM_REV0 | DRONE_META | DRONE_VENDOR | DRONE_POINTCLOUD | DRONE_IMAGE | DRONE_VIDEO
    file_name: str
    rel_path: str
    file_format: str
    revision: str
    revision_rank: int
    file_hash: str
    size_bytes: int
    doc_date: str = ""
    status: str = "REGISTERED"   # REGISTERED | CURRENT | SUPERSEDED | DUPLICATE
    source: str = "folder"

    def to_row(self) -> dict:
        return {k.upper(): v for k, v in asdict(self).items()}


@dataclass
class ExtractedField:
    doc_id: str
    site_id: str
    page: str
    field_name: str
    value: Any
    confidence: float
    method: str              # XLSX | PDF_TEXT | DXF_ATTR | OCR | CSV | JSON | POINTCLOUD | VIDEO
    needs_review: bool = False


@dataclass
class ConfigItem:
    """One piece of equipment as one source describes it (CONFIG_LINE)."""
    site_id: str
    source: str              # RFDS_EXISTING | RFDS_FINAL | CD | FIELD | MA_LOADING | REV0
    sector: str
    position: int | None
    kind: str                # passive | air | radio | pipe | sled
    catalog_key: str | None
    model_text: str
    status: str              # Existing | New | Remove | Retain
    rad_center_ft: float | None = None
    azimuth_deg: float | None = None
    mech_tilt: float | None = None
    bands: str = ""
    ref: SourceRef | None = None
    confidence: float = 1.0
    feeds_position: int | None = None
    attrs: dict = field(default_factory=dict)

    @property
    def is_device(self) -> bool:
        return self.kind in ("passive", "air", "radio")


@dataclass
class SectorInfo:
    code: str
    azimuth: dict[str, float] = field(default_factory=dict)   # by source
    new_frame: bool = False
    sled: dict[str, bool] = field(default_factory=dict)       # by source (CD / FIELD)


@dataclass
class TrunkInfo:
    source: str
    count: int | None
    vertical_ft: float | None
    horizontal_ft: float | None
    required_ft: float | None
    specified_ft: int | None
    ref: SourceRef | None = None


@dataclass
class AnalysisResult:
    kind: str                          # MA | SA
    report_id: str
    date: str
    result: str
    capacity_pct: float | None
    capacity_after_pct: float | None = None
    rfds_revision: str | None = None
    modifications: list[dict] = field(default_factory=list)   # {sector, kit_key, qty, text}
    loading: list[ConfigItem] = field(default_factory=list)
    ref: SourceRef | None = None


@dataclass
class Rev0Line:
    row: int
    sector: str              # A/B/C/D or SITE
    catalog_key: str | None
    model: str
    mfr_pn: str
    customer_pn: str
    design_qty: float
    spare_qty: float
    action: str
    rule_id: str
    source: str


@dataclass
class FieldObject:
    object_id: str
    object_type: str         # Antenna | Remote radio | Mount pipe | Roof sled | Cable route | Cabinet
    sector: str | None
    bearing_deg: float | None
    facing_az_deg: float | None
    center_height_ft: float | None
    dims_in: tuple[float, float, float] | None
    model_guess: str
    confidence: float
    route_length_ft: float | None = None
    method: str = "VENDOR_CSV"
    position: int | None = None


@dataclass
class VideoFrame:
    frame_index: int
    time_s: float
    bearing_deg: float
    sector: str | None
    sharpness: float
    path: str
    selected: bool = False


@dataclass
class SiteFacts:
    """Everything extracted for one site, input to reconcile / delta / generate."""
    site_id: str
    site: dict = field(default_factory=dict)            # SiteTracker + RFDS site info
    project: dict = field(default_factory=dict)
    milestones: list[dict] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    fields: list[ExtractedField] = field(default_factory=list)
    rfds_revision: str = ""
    rfds_date: str = ""
    rfds_history: list[dict] = field(default_factory=list)
    rfds_existing: list[ConfigItem] = field(default_factory=list)
    rfds_final: list[ConfigItem] = field(default_factory=list)
    basebands: list[dict] = field(default_factory=list)
    dc_load_added_w: float | None = None
    cd_items: list[ConfigItem] = field(default_factory=list)
    cd_rfds_reference: str | None = None
    cd_revision: str = ""
    cd_method: str = ""
    sectors: dict[str, SectorInfo] = field(default_factory=dict)
    trunks: dict[str, TrunkInfo] = field(default_factory=dict)          # by source: CD | FIELD
    ma: AnalysisResult | None = None
    sa: AnalysisResult | None = None
    rev0: list[Rev0Line] = field(default_factory=list)
    field_objects: list[FieldObject] = field(default_factory=list)
    field_items: list[ConfigItem] = field(default_factory=list)
    field_method: str = ""
    frames: list[VideoFrame] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_rooftop(self) -> bool:
        return "ROOF" in str(self.site.get("structure_type", "")).upper()

    def doc(self, doc_type: str) -> Document | None:
        cands = [d for d in self.documents if d.doc_type == doc_type and d.status == "CURRENT"]
        return max(cands, key=lambda d: d.revision_rank) if cands else None


# ---------------------------------------------------------------- engine outputs
@dataclass
class Discrepancy:
    disc_id: str
    site_id: str
    rule_id: str
    family: str
    severity: str            # LOW | MEDIUM | HIGH | CRITICAL
    outcome: str             # RFI | REDLINE | BOM_CHANGE | FLAG | ESCALATE | REVIEW
    title: str
    description: str
    sector: str | None = None
    position: int | None = None
    expected: Any = None     # what the governing source says
    found: Any = None        # what the other source / field shows
    governing: str = ""      # which source governs the outcome (e.g. RFDS governs RF)
    sources: list[str] = field(default_factory=list)     # SourceRef labels (traceability)
    target_doc: str = ""
    target_sheet: str = ""
    bom_impact: str = ""
    evidence: list[str] = field(default_factory=list)    # evidence frame paths / object ids
    status: str = "OPEN"
    confidence: float = 1.0


@dataclass
class DeltaLine:
    site_id: str
    sector: str
    position: int | None
    kind: str
    catalog_key: str | None
    action: str              # NEW | EXISTING | REMOVED | RELOCATED | REUSED
    from_position: int | None = None
    rad_center_ft: float | None = None
    basis: str = ""          # why (RFDS final, field survey, ...)
    ref: SourceRef | None = None


@dataclass
class BomLine:
    site_id: str
    sector: str              # A..D or SITE
    catalog_key: str
    design_qty: float
    spare_qty: float = 0
    action: str = "Install"  # Install | Remove
    rule_id: str = ""
    source: str = ""
    parent_key: str = ""
    reason_code: str = "RC-RULE-APPLIED"
    trace: dict = field(default_factory=dict)

    @property
    def total_qty(self) -> float:
        return self.design_qty + self.spare_qty


@dataclass
class DriverLine:
    site_id: str
    driver_code: str
    description: str
    qty: float
    uom: str
    unit_rate: float
    basis: str
    sector: str | None = None

    @property
    def amount(self) -> float:
        return round(self.qty * self.unit_rate, 2)


@dataclass
class Redline:
    redline_id: str
    site_id: str
    doc_type: str            # CD | MA_SA | RFDS
    doc_revision: str
    sheet: str
    disc_id: str
    markup: str              # the text written on the drawing
    change_from: str
    change_to: str
    status: str = "DRAFT"


@dataclass
class Rfi:
    rfi_id: str
    site_id: str
    to_party: str            # ERICSSON | AE_ENGINEER
    subject: str
    question: str
    proposed_answer: str
    disc_ids: list[str] = field(default_factory=list)
    status: str = "DRAFT"
