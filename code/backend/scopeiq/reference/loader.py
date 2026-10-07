"""Loads every versioned reference table (catalog, kit rules, consistency rules, driver matrix, rate cards,
site-requirement rules, cycle-time parameters, reason codes, personas, workflow) into one ReferenceData object.

Source is either the CSV library in code/reference_data (default, used offline and to seed Snowflake) or the
REF_* tables in the database (pass a repository). Rows are filtered by EFFECTIVE_FROM / EFFECTIVE_TO so a
site is always scoped on the rules in force on its scoping date (guide 10.1).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from scopeiq.common.errors import ReferenceDataError
from scopeiq.common.logging import get_logger, log_call
from scopeiq.config import get_settings
from scopeiq.reference.catalog import Catalog, CatalogItem

log = get_logger(__name__)

TABLES = {
    "material_catalog": "material_catalog.csv",
    "kit_rules": "kit_rules.csv",
    "trunk_steps": "trunk_steps.csv",
    "consistency_rules": "consistency_rules.csv",
    "service_driver_matrix": "service_driver_matrix.csv",
    "rate_card": "rate_card.csv",
    "site_requirement_rules": "site_requirement_rules.csv",
    "cycle_time_params": "cycle_time_params.csv",
    "reason_codes": "reason_codes.csv",
    "personas": "personas.csv",
    "users": "users.csv",
    "workflow_states": "workflow_states.csv",
    "workflow_transitions": "workflow_transitions.csv",
}


def _active(row: dict, on: date) -> bool:
    f, t = (row.get("EFFECTIVE_FROM") or "").strip(), (row.get("EFFECTIVE_TO") or "").strip()
    if f and date.fromisoformat(f) > on:
        return False
    if t and date.fromisoformat(t) < on:
        return False
    return str(row.get("ACTIVE", "Y")).upper() != "N"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if str(v).strip() != "" else default
    except ValueError:
        return default


@dataclass
class ReferenceData:
    as_of: date
    tables: dict[str, list[dict]]
    catalog: Catalog
    versions: dict[str, str] = field(default_factory=dict)

    def rows(self, table: str) -> list[dict]:
        return self.tables.get(table, [])

    @property
    def trunk_steps(self) -> list[tuple[int, str]]:
        return sorted((int(r["STEP_FT"]), r["CATALOG_KEY"]) for r in self.rows("trunk_steps"))

    @property
    def reason_codes(self) -> set[str]:
        return {r["REASON_CODE"] for r in self.rows("reason_codes")}

    def consistency_rule(self, rule_id: str) -> dict:
        for r in self.rows("consistency_rules"):
            if r["RULE_ID"] == rule_id:
                out = dict(r)
                out["PARAMS"] = json.loads(r.get("PARAMS_JSON") or "{}")
                return out
        raise ReferenceDataError(f"Consistency rule {rule_id} is not active", details={"rule_id": rule_id})

    def rule_active(self, rule_id: str, stream: str | None = None) -> bool:
        """Rule exists for the as-of date, is ACTIVE=Y and applies to the stream (STREAMS 'ALL' or ';'-list)."""
        for r in self.rows("consistency_rules"):
            if r["RULE_ID"] == rule_id:
                if str(r.get("ACTIVE", "Y")).upper() != "Y":
                    return False
                streams = str(r.get("STREAMS") or "ALL").upper()
                return stream is None or streams == "ALL" or stream.upper() in streams.split(";")
        return False

    def cycle_param(self, name: str, default: float = 0.0) -> float:
        for r in self.rows("cycle_time_params"):
            if r["PARAM"] == name:
                return _num(r["VALUE"], default)
        return default

    def rate(self, market: str, sp: str, driver: str) -> float | None:
        best = None
        for r in self.rows("rate_card"):
            if r["DRIVER_CODE"] != driver or r["MARKET"] not in (market, "*"):
                continue
            if r["SERVICE_PROVIDER"] == sp:
                return _num(r["UNIT_RATE_USD"])
            if r["SERVICE_PROVIDER"] == "*":
                best = _num(r["UNIT_RATE_USD"])
        return best


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()} for row in csv.DictReader(f)]


def _catalog_from_rows(rows: list[dict]) -> Catalog:
    items = []
    for r in rows:
        items.append(CatalogItem(
            key=r["CATALOG_KEY"], category=r["CATEGORY"], subcategory=r["SUBCATEGORY"], manufacturer=r["MANUFACTURER"],
            model=r["MODEL"], mfr_pn=r["MANUFACTURER_PN"], customer_pn=r["CUSTOMER_PN"], description=r["DESCRIPTION"],
            uom=r["UOM"], supply=r["SUPPLY"], approved=str(r["CUSTOMER_APPROVED"]).upper() == "Y",
            unit_cost=_num(r["UNIT_COST_USD"]), rf_ports=int(_num(r["RF_PORTS"])), power_w=_num(r["POWER_W"]),
            bands=r.get("BANDS", ""), technology=r.get("TECHNOLOGY", ""), height_m=_num(r["HEIGHT_M"]),
            width_m=_num(r["WIDTH_M"]), depth_m=_num(r["DEPTH_M"]),
            aliases=[a for a in (r.get("ALIASES") or "").split("|") if a]))
    if not items:
        raise ReferenceDataError("Material catalog is empty")
    return Catalog(items)


@log_call()
def load_reference(as_of: date | None = None, *, source_dir: Path | None = None, repository=None) -> ReferenceData:
    as_of = as_of or date.today()
    tables: dict[str, list[dict]] = {}
    if repository is not None:
        for name in TABLES:
            tables[name] = repository.fetch_reference(name)
        src = "database"
    else:
        folder = source_dir or get_settings().path("paths.reference_data_dir")
        for name, fn in TABLES.items():
            p = folder / fn
            if not p.exists():
                raise ReferenceDataError(f"Reference file missing: {p}", details={"table": name})
            tables[name] = _read_csv(p)
        src = str(folder)
    filtered = {k: [r for r in v if _active(r, as_of)] for k, v in tables.items()}
    versions = {k: max((str(r.get("VERSION", "1")) for r in v), default="-") for k, v in filtered.items()}
    log.info("reference data loaded from %s as of %s", src, as_of, extra={"row_counts": {k: len(v) for k, v in filtered.items()}})
    return ReferenceData(as_of=as_of, tables=filtered, catalog=_catalog_from_rows(filtered["material_catalog"]), versions=versions)
