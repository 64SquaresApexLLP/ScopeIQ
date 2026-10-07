"""Single schema registry for every table. Snowflake DDL (snowflake/*.sql) and the local SQLite database are
both generated from this module, so the two backends cannot drift.

Layers (Snowflake schemas): RAW (landing), REF (versioned reference data), CORE (pipeline results and business
records), WF (workflow events, notifications, comments), AUDIT (audit trail, application and error logs).

Column spec: "NAME TYPE [PK] [NN]" with TYPE one of
  S = text, N = decimal, I = integer, B = boolean, T = timestamp, D = date, V = JSON (VARIANT in Snowflake).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REF_DIR = Path(__file__).resolve().parents[3] / "reference_data"


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    pk: bool = False
    not_null: bool = False


@dataclass(frozen=True)
class Table:
    layer: str
    name: str
    columns: tuple[Column, ...]
    comment: str = ""

    @property
    def fqn(self) -> str:
        return f"{self.layer}.{self.name}"

    @property
    def pk(self) -> list[str]:
        return [c.name for c in self.columns if c.pk]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


def _cols(spec: str) -> tuple[Column, ...]:
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        bits = part.split()
        out.append(Column(bits[0].upper(), bits[1].upper(), "PK" in bits[2:], "NN" in bits[2:] or "PK" in bits[2:]))
    return tuple(out)


TABLES: dict[str, Table] = {}


def table(layer: str, name: str, spec: str, comment: str = "") -> Table:
    t = Table(layer, name, _cols(spec), comment)
    TABLES[t.fqn] = t
    return t


# ------------------------------------------------------------------ REF: built from the reference CSV headers
REF_FILES = {
    "MATERIAL_CATALOG": ("material_catalog.csv", ["CATALOG_KEY"]), "KIT_RULE": ("kit_rules.csv", ["RULE_ID", "VERSION"]),
    "TRUNK_STEP": ("trunk_steps.csv", ["STEP_FT", "VERSION"]), "CONSISTENCY_RULE": ("consistency_rules.csv", ["RULE_ID", "VERSION"]),
    "SERVICE_DRIVER_MATRIX": ("service_driver_matrix.csv", ["DRIVER_CODE", "VERSION"]),
    "RATE_CARD": ("rate_card.csv", ["MARKET", "SERVICE_PROVIDER", "DRIVER_CODE", "VERSION"]),
    "SITE_REQUIREMENT_RULE": ("site_requirement_rules.csv", ["RULE_ID", "VERSION"]), "CYCLE_TIME_PARAM": ("cycle_time_params.csv", ["PARAM", "VERSION"]),
    "REASON_CODE": ("reason_codes.csv", ["REASON_CODE"]), "PERSONA": ("personas.csv", ["ROLE_CODE"]), "APP_USER": ("users.csv", ["USER_ID"]),
    "WORKFLOW_STATE": ("workflow_states.csv", ["ENTITY_TYPE", "STATE"]),
    "WORKFLOW_TRANSITION": ("workflow_transitions.csv", ["ENTITY_TYPE", "FROM_STATE", "ACTION"]),
}
NUMERIC = {"UNIT_COST_USD", "RF_PORTS", "POWER_W", "HEIGHT_M", "WIDTH_M", "DEPTH_M", "STEP_FT", "UNIT_RATE_USD", "PRIORITY", "MIN_HEIGHT_FT",
           "MAX_HEIGHT_FT", "MIN_NEW_LOAD_LB", "CRANE_DAYS", "MANLIFT_DAYS", "VALUE", "SEQ", "VERSION"}
DATES = {"EFFECTIVE_FROM", "EFFECTIVE_TO"}
# reference CSV file name per REF table, for loaders/seeding
REF_TABLE_FILES = {name: f for name, (f, _) in REF_FILES.items()}

for _name, (_file, _pk) in REF_FILES.items():
    with open(REF_DIR / _file, newline="", encoding="utf-8-sig") as _f:
        _hdr = next(csv.reader(_f))
    _spec = ", ".join(f"{h} {'N' if h in NUMERIC else 'D' if h in DATES else 'S'}{' PK' if h in _pk else ''}" for h in _hdr)
    table("REF", _name, _spec + ", LOADED_AT T, LOADED_BY S", f"Reference data from {_file} (versioned, effective-dated)")

# ------------------------------------------------------------------ RAW (Snowflake landing)
table("RAW", "ST_SITE", "ID S PK, NAME S, SITE_NAME__C S, MARKET__C S, CUSTOMER__C S, STREET__C S, CITY__C S, STATE__C S, ZIP__C S, "
      "LATITUDE__C N, LONGITUDE__C N, STRUCTURE_TYPE__C S, STRUCTURE_HEIGHT_FT__C N, STRUCTURE_OWNER__C S, SITE_STATUS__C S, LOADED_AT T",
      "SiteTracker Site export")
table("RAW", "ST_PROJECT", "ID S PK, NAME S, SITE__C S, PROJECT_TYPE__C S, SCOPING_SERVICE_LINE__C S, SCOPING_ASSIGNED_DATE__C S, BOM_STATUS__C S, "
      "CURRENT_BOM_REV__C S, CX_SERVICE_PROVIDER__C S, SCOPING_COMPLETE_FORECAST__C S, SCOPING_COMPLETE_ACTUAL__C S, FBA_DATE__C S, LOADED_AT T",
      "SiteTracker Project export")
table("RAW", "ST_MILESTONE", "ID S PK, PROJECT__C S, NAME S, FORECAST_DATE__C S, ACTUAL_DATE__C S, STATUS__C S, SEQUENCE__C N, LOADED_AT T",
      "SiteTracker Milestone export")
table("RAW", "ST_DOCUMENT", "ID S PK, PROJECT__C S, DOCUMENT_TYPE__C S, TITLE S, FILE_PATH__C S, FILE_FORMAT__C S, REVISION__C S, "
      "UPLOADED_DATE__C S, LOADED_AT T", "SiteTracker Document export")

# ------------------------------------------------------------------ CORE
table("CORE", "SITE", "SITE_ID S PK, SF_ID S, SITE_NAME S, MARKET S, CUSTOMER S, ADDRESS S, CITY S, STATE S, ZIP S, LATITUDE N, LONGITUDE N, "
      "STRUCTURE_TYPE S, HEIGHT_FT N, STRUCTURE_OWNER S, SITE_STATUS S, STREAM S, PROJECT_SF_ID S, PROJECT_NAME S, PROJECT_TYPE S, "
      "SERVICE_LINE S, CX_SP S, ASSIGNED_DATE S, SCOPING_FORECAST S, SCOPING_ACTUAL S, FBA_DATE S, CURRENT_BOM_REV S, WORKFLOW_STATE S, "
      "ASSIGNED_TO S, LAST_RUN_ID S, UPDATED_AT T, UPDATED_BY S", "One row per site (SiteTracker + RFDS site info + workflow state)")
table("CORE", "MILESTONE", "MILESTONE_SF_ID S PK, SITE_ID S NN, NAME S, SEQ I, FORECAST S, ACTUAL S, STATUS S", "SiteTracker milestones")
table("CORE", "DOCUMENT", "DOC_ID S PK, SITE_ID S NN, DOC_TYPE S, FILE_NAME S, REL_PATH S, FILE_FORMAT S, REVISION S, REVISION_RANK I, FILE_HASH S, "
      "SIZE_BYTES I, DOC_DATE S, SOURCE S, STATUS S, REGISTERED_AT T, REGISTERED_BY S", "Document registry (latest revision = CURRENT)")
table("CORE", "UPLOAD", "UPLOAD_ID S PK, SITE_ID S NN, DOC_TYPE S, FILE_NAME S, STAGE_PATH S, SIZE_BYTES I, FILE_HASH S, UPLOADED_BY S, "
      "UPLOADED_AT T, STATUS S, DOC_ID S, MESSAGE S", "Artifacts uploaded through the app before registration")
table("CORE", "PIPELINE_RUN", "RUN_ID S PK, SITE_ID S NN, STARTED_AT T, FINISHED_AT T, STATUS S, TRIGGERED_BY S, CORRELATION_ID S, "
      "STEPS V, SUMMARY V, WARNINGS V, REFERENCE_VERSIONS V", "One row per pipeline execution for a site")
table("CORE", "EXTRACTED_FIELD", "FIELD_ID S PK, RUN_ID S, SITE_ID S NN, DOC_ID S, PAGE S, FIELD_NAME S, VALUE V, CONFIDENCE N, METHOD S, "
      "NEEDS_REVIEW B, REVIEWED_BY S, REVIEWED_AT T", "Every value read from a document, with confidence")
table("CORE", "CONFIG_LINE", "LINE_ID S PK, RUN_ID S, SITE_ID S NN, SOURCE S, SECTOR S, POSITION I, KIND S, CATALOG_KEY S, MODEL_TEXT S, STATUS S, "
      "RAD_CENTER_FT N, AZIMUTH_DEG N, MECH_TILT N, BANDS S, SOURCE_REF S, CONFIDENCE N, ATTRS V", "Equipment per source (RFDS/CD/FIELD/MA)")
table("CORE", "SECTOR_INFO", "SITE_ID S PK, RUN_ID S PK, SECTOR S PK, AZ_RFDS N, AZ_CD N, AZ_FIELD N, NEW_FRAME B, SLED_CD B, SLED_FIELD B",
      "Sector azimuths and mounts per source")
table("CORE", "TRUNK_MEASURE", "SITE_ID S PK, RUN_ID S PK, SOURCE S PK, TRUNK_COUNT I, VERTICAL_FT N, HORIZONTAL_FT N, REQUIRED_FT N, "
      "SPECIFIED_FT N, SOURCE_REF S", "Cable schedule (CD) and measured route (FIELD)")
table("CORE", "ANALYSIS_RESULT", "SITE_ID S PK, RUN_ID S PK, KIND S PK, REPORT_ID S, REPORT_DATE S, RESULT S, CAPACITY_PCT N, CAPACITY_AFTER_PCT N, "
      "RFDS_REVISION S, MODIFICATIONS V, SOURCE_REF S", "Mount (MA) and structural (SA) analysis results")
table("CORE", "REV0_LINE", "SITE_ID S PK, RUN_ID S PK, ROW_NUM I PK, SECTOR S, CATALOG_KEY S, MODEL S, MFR_PN S, CUSTOMER_PN S, DESIGN_QTY N, "
      "SPARE_QTY N, ACTION S, RULE_ID S, SOURCE S", "REV 0 preliminary BOM rows as read")
table("CORE", "FIELD_OBJECT", "SITE_ID S PK, RUN_ID S PK, OBJECT_ID S PK, OBJECT_TYPE S, SECTOR S, POSITION I, BEARING_DEG N, FACING_AZ_DEG N, "
      "CENTER_HEIGHT_FT N, DIMS_IN V, MODEL_GUESS S, CONFIDENCE N, ROUTE_LENGTH_FT N, METHOD S", "Drone survey objects (vendor CSV or point cloud)")
table("CORE", "EVIDENCE_FRAME", "FRAME_ID S PK, RUN_ID S, SITE_ID S NN, FRAME_INDEX I, TIME_S N, BEARING_DEG N, SECTOR S, SHARPNESS N, PATH S, "
      "SELECTED B", "Frames sampled from the drone orbit video")
table("CORE", "DISCREPANCY", "DISC_ID S PK, SITE_ID S NN, RUN_ID S, RULE_ID S, FAMILY S, SEVERITY S, OUTCOME S, TITLE S, DESCRIPTION S, SECTOR S, "
      "POSITION I, EXPECTED V, FOUND V, GOVERNING S, SOURCES V, TARGET_DOC S, TARGET_SHEET S, BOM_IMPACT S, EVIDENCE V, CONFIDENCE N, "
      "STATUS S, REASON_CODE S, ASSIGNED_TO S, FIRST_SEEN_RUN S, LAST_SEEN_RUN S, CREATED_AT T, UPDATED_AT T, UPDATED_BY S",
      "Findings; id is stable across runs so human decisions survive re-runs")
table("CORE", "EQUIPMENT_DELTA", "SITE_ID S PK, RUN_ID S PK, SEQ I PK, SECTOR S, POSITION I, KIND S, CATALOG_KEY S, ACTION S, FROM_POSITION I, "
      "RAD_CENTER_FT N, BASIS S, SOURCE_REF S", "NEW / EXISTING / REMOVED / RELOCATED / REUSED per device")
table("CORE", "BOM_REVISION", "BOM_REV_ID S PK, SITE_ID S NN, REV_NO I, REV_LABEL S, KIND S, STATUS S, LOCKED B, RUN_ID S, PARENT_REV_ID S, "
      "REASON_CODE S, TRUNK_PLAN V, TOTALS V, CREATED_AT T, CREATED_BY S, APPROVED_AT T, APPROVED_BY S, NOTES S",
      "BOM revisions: REV 0 (tool), REV 1..n (generated/edited); FBA revisions are locked")
table("CORE", "BOM_LINE", "LINE_ID S PK, BOM_REV_ID S NN, SITE_ID S NN, SECTOR S, CATALOG_KEY S, DESIGN_QTY N, SPARE_QTY N, TOTAL_QTY N, ACTION S, "
      "RULE_ID S, SOURCE S, PARENT_KEY S, REASON_CODE S, TRACE V, EDITED_BY S, EDITED_AT T", "BOM lines with rule ID and source reference")
table("CORE", "BOM_CHANGE", "CHANGE_ID S PK, SITE_ID S NN, FROM_REV_ID S, TO_REV_ID S, SECTOR S, CATALOG_KEY S, ACTION S, FROM_QTY N, TO_QTY N, "
      "DELTA N, REASONS V", "Line-level differences between two revisions with reasons")
table("CORE", "DRIVER_LINE", "LINE_ID S PK, RUN_ID S, SITE_ID S NN, DRIVER_CODE S, DESCRIPTION S, SECTOR S, QTY N, UOM S, UNIT_RATE N, AMOUNT N, "
      "BASIS S", "Service drivers (FPP codes) with illustrative rates")
table("CORE", "SITE_REQUIREMENT", "SITE_ID S PK, RUN_ID S PK, RULE_ID S, ACCESS_METHOD S, CRANE_DAYS N, MANLIFT_DAYS N, RIGGING_CLASS S, HOLD B, "
      "INPUTS V", "Access, rigging and hold requirements")
table("CORE", "ESTIMATE", "SITE_ID S PK, RUN_ID S PK, CYCLE_DAYS N, SERVICES_USD N, MATERIAL_USD N, TOTAL_USD N, DETAIL V", "Cost and cycle-time estimate")
table("CORE", "EHS_ALERT", "ALERT_ID S PK, SITE_ID S NN, RULE_ID S, SEVERITY S, ALERT_TEXT S, STATUS S, CREATED_AT T, UPDATED_AT T, UPDATED_BY S",
      "EH&S alerts (rooftop crane, guyed tower, SA fail)")
table("CORE", "REDLINE", "REDLINE_ID S PK, SITE_ID S NN, DISC_ID S, DOC_TYPE S, DOC_REVISION S, SHEET S, MARKUP S, CHANGE_FROM S, CHANGE_TO S, "
      "STATUS S, PDF_PATH S, CREATED_AT T, UPDATED_AT T, UPDATED_BY S", "Redlines to apply to CD / MA documents")
table("CORE", "RFI", "RFI_ID S PK, SITE_ID S NN, TO_PARTY S, SUBJECT S, QUESTION S, PROPOSED_ANSWER S, ANSWER S, DISC_IDS V, STATUS S, CREATED_AT T, "
      "UPDATED_AT T, UPDATED_BY S", "Requests for information")

# ------------------------------------------------------------------ WF
table("WF", "WORKFLOW_EVENT", "EVENT_ID S PK, ENTITY_TYPE S NN, ENTITY_ID S NN, SITE_ID S, FROM_STATE S, ACTION S, TO_STATE S, ACTOR_USER_ID S, "
      "ACTOR_ROLE S, REASON_CODE S, COMMENT S, EVENT_TS T, CORRELATION_ID S", "Every workflow transition (status history)")
table("WF", "NOTIFICATION", "NOTIFICATION_ID S PK, ROLE_CODE S, USER_ID S, SITE_ID S, ENTITY_TYPE S, ENTITY_ID S, MESSAGE S, CREATED_AT T, READ_AT T",
      "Role inbox items created by transitions")
table("WF", "COMMENT", "COMMENT_ID S PK, ENTITY_TYPE S, ENTITY_ID S, SITE_ID S, USER_ID S, COMMENT_TEXT S, CREATED_AT T", "Free-text comments")

# ------------------------------------------------------------------ AUDIT
table("AUDIT", "AUDIT_LOG", "AUDIT_ID S PK, EVENT_TS T, ENTITY_TYPE S, ENTITY_ID S, SITE_ID S, ACTION S, ACTOR_USER_ID S, ACTOR_ROLE S, REASON_CODE S, "
      "COMMENT S, BEFORE_VALUE V, AFTER_VALUE V, CORRELATION_ID S, SOURCE S", "Who changed what, when and why (immutable)")
table("AUDIT", "APP_LOG", "LOG_ID S PK, LOG_TS T, LEVEL S, LOGGER S, MESSAGE S, CORRELATION_ID S, USER_ID S, SITE_ID S, COMPONENT S, DETAIL V",
      "Application log sink (level set per environment)")
table("AUDIT", "ERROR_LOG", "ERROR_ID S PK, ERROR_TS T, ERROR_CODE S, MESSAGE S, EXCEPTION_TYPE S, STACK S, WHERE_RAISED S, CORRELATION_ID S, "
      "USER_ID S, SITE_ID S, COMPONENT S, DETAILS V", "Errors with stack and context")

LAYERS = ["RAW", "REF", "CORE", "WF", "AUDIT"]


def tables(layer: str | None = None) -> list[Table]:
    return [t for t in TABLES.values() if layer is None or t.layer == layer]


def get_table(fqn: str) -> Table:
    return TABLES[fqn.upper()]
