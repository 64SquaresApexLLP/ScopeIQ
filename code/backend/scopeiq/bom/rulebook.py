"""The BOM rulebook, read straight from `bom_rules.xlsx` and `material_catalog.xlsx` (Data/Reference-Data).

The Excel files are the source of truth. They are written for people, so a rule says "New remote radio" and "1 per radio", not
TRIGGER_CODE and QTY_EXPR. This module reads them again at every run and interprets the text into structured rules:

  * Columns are found by their header name, so column order, extra columns, blank rows and notes under the table do not matter.
  * A rule whose trigger or quantity text is not understood is NOT APPLIED and reported with the reason. It never stops the run
    and it is never guessed at.
  * Numbers that the sheets state only in words (the trunk length factor, the tower margin) are read from the sheet's own note.
    If the note is missing or cannot be read, trunks are held and the reason is reported; no value is assumed.
  * The rulebook revision is a fingerprint of the two files, so every BOM line says which version of the rules produced it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import openpyxl

from scopeiq.common.errors import ReferenceDataError
from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings
from scopeiq.reference.catalog import Catalog, CatalogItem
from scopeiq.reference.expressions import evaluate

log = get_logger(__name__)

# Trigger text -> the situation the engine detects. Order matters: the first pattern that matches wins.
TRIGGERS: list[tuple[str, str]] = [
    ("NEW_RADIO_TO_PASSIVE", r"new remote radio.*feeding a passive"),
    ("NEW_RADIO", r"new remote radio"),
    ("NEW_AAU", r"new (aau|active antenna)"),
    ("NEW_PASSIVE", r"new passive antenna"),
    ("POSITION_NO_PIPE", r"(new|any) .*(antenna|aau|device).*no mount pipe"),
    ("SECTOR_NEW_FRAME", r"sector marked for new frame"),
    ("ROOF_SECTOR_NO_SLED", r"rooftop sector.*no roof sled"),
    ("MA_REINFORCEMENT", r"mount analysis requires reinforcement"),
    ("SECTOR_NEW_DEVICE", r"sector with any new device"),
    ("TRUNK", r"new powered devices"),
    ("PER_TRUNK", r"per (hybrid )?trunk"),
    ("PER_OVP", r"per ovp"),
    ("NEW_BASEBAND", r"new baseband"),
    ("NET_DC_LOAD", r"net new dc load"),
    ("PER_SITE", r"per site"),
    ("NEW_MAJOR", r"new major equipment"),
    ("REMOVE_DEVICE", r"equipment to remove|remove"),
]
# Words used in quantity text -> the variable the engine provides for that trigger.
QTY_WORDS = {"powered devices": "powered_new", "devices": "powered_new", "trunk length ft": "trunk_length_ft", "trunk length": "trunk_length_ft",
             "length": "trunk_length_ft", "added w": "added_w", "removed w": "removed_w", "ports": "ports", "ma qty": "ma_qty"}
_VARS = {"powered_new": 6, "trunk_length_ft": 100, "added_w": 3000, "removed_w": 0, "ports": 4, "ma_qty": 1}


class RulebookError(ReferenceDataError):
    code = "SIQ-REF-500"


@dataclass
class Rule:
    rule_id: str
    trigger_text: str
    trigger: str | None
    child: str
    qty_text: str
    qty_expr: str | None
    spare_expr: str
    notes: str
    status: str = "APPLIED"          # APPLIED | NOT APPLIED
    problem: str = ""

    @property
    def applied(self) -> bool:
        return self.status == "APPLIED"


@dataclass
class Rulebook:
    rules: list[Rule]
    catalog: Catalog
    trunk_steps: list[tuple[int, str]]
    length_factor: float | None
    tower_margin_ft: float | None
    issues: list[dict] = field(default_factory=list)
    revision: str = ""
    files: dict = field(default_factory=dict)

    def by_trigger(self, trigger: str) -> list[Rule]:
        return [r for r in self.rules if r.applied and r.trigger == trigger]

    def summary(self) -> dict:
        return {"revision": self.revision, "files": self.files, "rules": len(self.rules), "applied": sum(r.applied for r in self.rules),
                "not_applied": [{"rule_id": r.rule_id, "problem": r.problem} for r in self.rules if not r.applied],
                "catalog_items": len(self.catalog.items), "trunk_steps": len(self.trunk_steps), "length_factor": self.length_factor,
                "tower_margin_ft": self.tower_margin_ft}


# ------------------------------------------------------------------------------------------------ reading the sheets
def _h(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _col(cols: dict[str, int], name: str) -> int | None:
    if name in cols:
        return cols[name]
    return next((j for k, j in cols.items() if k.startswith(name)), None)


def _table(ws, required: list[str]) -> tuple[dict[str, int], list[tuple]]:
    """Find the header row (the first row holding every required header) and return {header: column} plus the rows under it."""
    rows = list(ws.iter_rows(values_only=True))
    for i, row in enumerate(rows):
        cols = {_h(c): j for j, c in enumerate(row) if c not in (None, "")}
        if all(_col(cols, r) is not None for r in required):
            return cols, rows[i + 1:]
    raise RulebookError(f"Sheet '{ws.title}' has no header row with: {', '.join(required)}", details={"sheet": ws.title})


def aliases(model: str) -> list[str]:
    """Spellings seen on drawings and RFDS for the same model (OCR and A&E variants)."""
    up = model.upper()
    out = {up, up.replace(" ", ""), up.replace("RADIO ", "")}
    m = re.match(r"AIR (\d+)", up)
    if m:
        out.add(f"AIR{m.group(1)}")
    return sorted(a for a in out if a and a != up)


def read_catalog(path: Path) -> list[CatalogItem]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = next((s for s in wb.worksheets if "catalog" in s.title.lower()), wb.worksheets[0])
    cols, rows = _table(ws, ["catalogkey", "category", "subcategory", "model"])

    def g(r, n):
        j = _col(cols, n)
        return r[j] if j is not None and j < len(r) else None

    items, seen = [], set()
    for r in rows:
        key, cat, sub = _text(g(r, "catalogkey")), _text(g(r, "category")), _text(g(r, "subcategory"))
        if not key or not cat or not sub or key in seen:        # blank rows, the note under the table, duplicates
            continue
        seen.add(key)
        model = _text(g(r, "model"))
        items.append(CatalogItem(
            key=key, category=cat, subcategory=sub, manufacturer=_text(g(r, "manufacturer")), model=model, mfr_pn=_text(g(r, "manufacturerpn")),
            customer_pn=_text(g(r, "customerpn")), description=_text(g(r, "description")), uom=_text(g(r, "uom")) or "EA",
            supply=_text(g(r, "supply")), approved=_text(g(r, "customerapproved")).upper() == "Y", unit_cost=_num(g(r, "unitcost")),
            rf_ports=int(_num(g(r, "rfports"))), power_w=_num(g(r, "power")), bands=_text(g(r, "bands")), technology=_text(g(r, "technology")),
            height_m=_num(g(r, "height")), width_m=_num(g(r, "width")), depth_m=_num(g(r, "depth")), aliases=aliases(model)))
    if not items:
        raise RulebookError(f"No catalog items found in {path.name}", details={"file": path.name})
    return items


# ------------------------------------------------------------------------------------------------ interpreting the text
def interpret_trigger(text: str) -> str | None:
    t = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    return next((code for code, pat in TRIGGERS if re.search(pat, t)), None)


def interpret_quantity(text: str) -> tuple[str | None, str, str]:
    """(quantity expression, spare expression, problem). The expression uses the variables the engine provides for the trigger."""
    t = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if not t:
        return None, "0", "no quantity is given"
    spare = "0"
    m = re.search(r"\(\s*\+\s*(\d+(?:\.\d+)?)\s*spare\s*\)", t)
    if m:
        spare, t = m.group(1), (t[:m.start()] + t[m.end():]).strip()
    m = re.fullmatch(r"\+\s*(\d+(?:\.\d+)?)\s*spare(?: per [a-z ]+)?", t)
    if m:
        return "0", m.group(1), ""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", t)
    if m:
        return m.group(1), spare, ""
    m = re.fullmatch(r"(\d+(?:\.\d+)?) per trunk if (?:trunk )?length\s*>\s*(\d+(?:\.\d+)?)\s*(?:ft)?,?\s*else (\d+(?:\.\d+)?)", t)
    if m:
        return f"{m.group(1)} if trunk_length_ft > {m.group(2)} else {m.group(3)}", spare, ""
    m = re.fullmatch(r"(\d+(?:\.\d+)?) per [a-z ]+", t)
    if m:
        return m.group(1), spare, ""
    if t in ("ports per radio", "ports"):
        return "ports", spare, ""
    if t in ("per ma", "ma qty", "per ma report"):
        return "ma_qty", spare, ""
    m = re.fullmatch(r"((?:ceil|floor|max|min|round)\(.*\))(?: per [a-z ]+| trunks?)?", t)
    if m:
        expr = m.group(1)
        for words, var in sorted(QTY_WORDS.items(), key=lambda kv: -len(kv[0])):
            expr = re.sub(rf"\b{re.escape(words)}\b", var, expr)
        unknown = sorted(set(re.findall(r"[a-z_]+", re.sub(r"\b(ceil|floor|max|min|round|abs|int|if|else)\b", "", expr))) - set(_VARS))
        if unknown:
            return None, spare, f"quantity term not understood: {', '.join(unknown)}"
        return expr, spare, ""
    return None, spare, f"quantity text not understood: '{text}'"


def read_rules(path: Path) -> tuple[list[Rule], list[tuple[int, str]], float | None, float | None]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = next((s for s in wb.worksheets if "rule" in s.title.lower()), wb.worksheets[0])
    cols, rows = _table(ws, ["ruleid", "trigger", "child", "quantity"])

    def g(r, n):
        j = _col(cols, n)
        return r[j] if j is not None and j < len(r) else None

    rules, seen = [], set()
    for r in rows:
        rid, child = _text(g(r, "ruleid")), _text(g(r, "child"))
        if not rid or not child:
            continue
        trig, qty = _text(g(r, "trigger")), _text(g(r, "quantity"))
        rule = Rule(rid, trig, interpret_trigger(trig), child, qty, None, "0", _text(g(r, "notes")))
        rule.qty_expr, rule.spare_expr, problem = interpret_quantity(qty)
        if rid in seen:
            rule.status, rule.problem = "NOT APPLIED", f"rule id {rid} appears more than once; the first one is used"
        elif rule.trigger is None:
            rule.status, rule.problem = "NOT APPLIED", f"trigger text not understood: '{trig}'"
        elif problem:
            rule.status, rule.problem = "NOT APPLIED", problem
        else:
            try:
                evaluate(rule.qty_expr, _VARS)
                evaluate(rule.spare_expr, _VARS)
            except Exception as exc:  # noqa: BLE001
                rule.status, rule.problem = "NOT APPLIED", f"quantity cannot be evaluated: {exc}"
        seen.add(rid)
        rules.append(rule)
    if not rules:
        raise RulebookError(f"No rules found in {path.name}", details={"file": path.name})
    # trunk lengths, and the note under them that gives the length factor and the tower margin
    steps: list[tuple[int, str]] = []
    note = ""
    ts = next((s for s in wb.worksheets if "trunk" in s.title.lower()), None)
    for row in (ts.iter_rows(values_only=True) if ts else []):
        a, b = (row[0] if row else None), (row[1] if len(row) > 1 else None)
        if isinstance(a, (int, float)) and b:
            steps.append((int(a), _text(b)))
        elif isinstance(a, str) and re.search(r"required length", a, re.I):
            note = a
    factor = margin = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*[x*]\s*\(?\s*vertical", note, re.I)
    if m:
        factor = float(m.group(1))
    m = re.search(r"rad(?:ius)? center\s*\+\s*(\d+(?:\.\d+)?)\s*ft", note, re.I)
    if m:
        margin = float(m.group(1))
    return rules, sorted(steps), factor, margin


# ------------------------------------------------------------------------------------------------ the rulebook
def _file(setting: str, default_name: str) -> Path:
    st = get_settings()
    if st.get(setting, None):
        return Path(st.path(setting))
    return Path(st.path("paths.reference_xlsx_dir")) / default_name


def load_rulebook(rules_path: Path | None = None, catalog_path: Path | None = None) -> Rulebook:
    """Read both Excel files now. Raises RulebookError only when a file is missing or unreadable (no BOM can be made without them)."""
    rp = Path(rules_path or _file("paths.bom_rules_file", "bom_rules.xlsx"))
    cp = Path(catalog_path or _file("paths.material_catalog_file", "material_catalog.xlsx"))
    for p in (rp, cp):
        if not p.exists():
            raise RulebookError(f"BOM reference file not found: {p.name}. It must be in {p.parent}.", details={"file": str(p)})
    try:
        items = read_catalog(cp)
        rules, steps, factor, margin = read_rules(rp)
    except RulebookError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RulebookError(f"BOM reference files could not be read: {exc}", cause=exc) from exc
    catalog = Catalog(items)
    issues: list[dict] = []
    sha = hashlib.sha256(rp.read_bytes() + cp.read_bytes()).hexdigest()[:8]
    for r in rules:
        if not r.applied:
            issues.append({"severity": "MEDIUM", "code": "RULE_NOT_APPLIED", "rule_id": r.rule_id, "message": f"{r.rule_id} is not applied: {r.problem}"})
        elif r.child != "(device)" and not r.child.endswith("*") and r.child not in catalog:
            r.status, r.problem = "NOT APPLIED", f"child item '{r.child}' is not in the material catalog"
            issues.append({"severity": "HIGH", "code": "RULE_CHILD_UNKNOWN", "rule_id": r.rule_id, "message": f"{r.rule_id} is not applied: {r.problem}"})
    for _, key in steps:
        if key not in catalog:
            issues.append({"severity": "HIGH", "code": "TRUNK_KEY_UNKNOWN", "rule_id": "", "message": f"Trunk length item '{key}' is not in the material catalog"})
    if not steps:
        issues.append({"severity": "HIGH", "code": "NO_TRUNK_LENGTHS", "rule_id": "", "message": "The Trunk Lengths sheet lists no lengths: hybrid trunks cannot be sized"})
    if factor is None:
        issues.append({"severity": "HIGH", "code": "NO_LENGTH_FACTOR", "rule_id": "", "message": "The Trunk Lengths note does not state the length factor "
                       "(e.g. 'Required length = 1.10 x (vertical + horizontal run)'): trunk lines are held"})
    if margin is None:
        issues.append({"severity": "MEDIUM", "code": "NO_TOWER_MARGIN", "rule_id": "", "message": "The Trunk Lengths note does not state the tower vertical margin "
                       "(e.g. 'highest new radio/AAU rad center + 5 ft'): trunk lines on towers are held"})
    when = datetime.fromtimestamp(max(rp.stat().st_mtime, cp.stat().st_mtime)).date().isoformat()
    log.info("rulebook %s: %d rules (%d applied), %d catalog items", sha, len(rules), sum(r.applied for r in rules), len(items))
    return Rulebook(rules, catalog, steps, factor, margin, issues, f"Rules {sha} ({when})",
                    {"rules": rp.name, "catalog": cp.name, "rules_modified": datetime.fromtimestamp(rp.stat().st_mtime).isoformat(timespec="seconds"),
                     "catalog_modified": datetime.fromtimestamp(cp.stat().st_mtime).isoformat(timespec="seconds")})
