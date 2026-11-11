"""Loads the ScopeIQ reference tables (SCOPEIQ_DB.REF) from the files in reference_data/.

    python scripts/load_reference.py             # load what is empty, report what is unchanged or different
    python scripts/load_reference.py --dry-run   # read and check the files, change nothing
    python scripts/load_reference.py --new-version   # a changed rulebook becomes the next VERSION (old rows are kept, their EFFECTIVE_TO is set)

Safe to run again: a table that already holds exactly this content is left alone, nothing is ever deleted or replaced,
and a table whose content differs is reported and left as it is unless --new-version is given (versioned tables only).
Connects with the Snowflake CLI connection named in SNOWFLAKE_CONNECTION (default "scopeiq"); no secrets in this file."""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent / "reference_data"
TODAY = dt.date.today()
DB, SCHEMA = "SCOPEIQ_DB", "REF"


def clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def num(v):
    v = clean(v)
    if v is None:
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        raise ValueError(f"not a number: {v!r}")


def day(v):
    v = clean(v)
    return None if v is None else (v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v)[:10]))


def yes(v):
    v = clean(v)
    return None if v is None else str(v).upper() in ("Y", "YES", "TRUE", "1")


# ------------------------------------------------------------------ readers: each returns (columns, rows)
def read_bom_rules():
    ws = openpyxl.load_workbook(ROOT / "bom_rules.xlsx", data_only=True)["BOM Rules"]
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if clean(r[0])]
    cols = ["RULE_ID", "SEQ", "TRIGGER_TEXT", "CHILD_ITEM", "QUANTITY_TEXT", "NOTES", "ACTIVE", "EFFECTIVE_FROM"]
    return cols, [[clean(r[0]), i, clean(r[1]), clean(r[2]), clean(r[3]), clean(r[4]), True, TODAY] for i, r in enumerate(rows, 1)]


def read_trunk():
    ws = openpyxl.load_workbook(ROOT / "bom_rules.xlsx", data_only=True)["Trunk Lengths"]
    steps, note = [], None
    for a, b, *_ in ws.iter_rows(min_row=2, values_only=True):
        if isinstance(a, (int, float)) and clean(b):
            steps.append((a, clean(b)))
        elif isinstance(a, str) and a.strip() and not b:
            note = a.strip()
    # the sheet's note states the sizing factor and tower margin; if it does not, they stay empty (nothing is assumed)
    f = re.search(r"(\d+(?:\.\d+)?)\s*x\s*\(", note or "")
    m = re.search(r"\+\s*(\d+(?:\.\d+)?)\s*ft", note or "")
    factor, margin = (float(f.group(1)) if f else None), (float(m.group(1)) if m else None)
    cols = ["STEP_FT", "CATALOG_KEY", "TRUNK_FACTOR", "TOWER_MARGIN_FT", "NOTE", "EFFECTIVE_FROM"]
    return cols, [[num(s), k, factor, margin, note, TODAY] for s, k in steps]


CATALOG = ["CATALOG_KEY", "CATEGORY", "SUBCATEGORY", "MANUFACTURER", "MODEL", "MANUFACTURER_PN", "CUSTOMER_PN", "DESCRIPTION", "UOM", "SUPPLY",
           "CUSTOMER_APPROVED", "UNIT_COST_USD", "RF_PORTS", "POWER_W", "BANDS", "TECHNOLOGY", "HEIGHT_M", "WIDTH_M", "DEPTH_M"]
CATALOG_NUM = {"UNIT_COST_USD", "RF_PORTS", "POWER_W", "HEIGHT_M", "WIDTH_M", "DEPTH_M"}


def read_catalog():
    ws = openpyxl.load_workbook(ROOT / "material_catalog.xlsx", data_only=True).active
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not clean(r[0]) or sum(1 for x in r[1:] if clean(x) is not None) < 3:      # blank lines and the "SYNTHETIC ..." footnote
            continue
        out.append([num(v) if CATALOG[i] in CATALOG_NUM else clean(v) for i, v in enumerate(r[:19])])
    return CATALOG, out


def read_csv(name, num_cols=(), date_cols=(), bool_cols=(), json_cols=()):
    with open(ROOT / name, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = [h.strip().upper() for h in rd.fieldnames]
        rows = []
        for rec in rd:
            row = []
            for h, raw in zip(cols, rec.values()):
                row.append(num(raw) if h in num_cols else day(raw) if h in date_cols else yes(raw) if h in bool_cols
                           else (json.dumps(json.loads(raw)) if clean(raw) else None) if h in json_cols else clean(raw))
            rows.append(row)
    return cols, rows


# table -> (reader, versioned, key columns used to describe differences)
TABLES = {
    "BOM_RULE": (read_bom_rules, True),
    "TRUNK_STEP": (read_trunk, True),
    "MATERIAL_CATALOG": (read_catalog, True),
    "CONSISTENCY_RULE": (lambda: read_csv("consistency_rules.csv", {"VERSION"}, {"EFFECTIVE_FROM", "EFFECTIVE_TO"}, {"ACTIVE"}, {"PARAMS_JSON"}), True),
    "REASON_CODE": (lambda: read_csv("reason_codes.csv"), False),
    "PERSONA": (lambda: read_csv("personas.csv"), False),
    "WORKFLOW_STATE": (lambda: read_csv("workflow_states.csv", {"SEQ"}), False),
    "WORKFLOW_TRANSITION": (lambda: read_csv("workflow_transitions.csv"), False),
}


def norm(v):
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v if not isinstance(v, str) else json.dumps(json.loads(v), sort_keys=True) if v[:1] in "{[" and _is_json(v) else v
    if isinstance(v, (int, float)) or hasattr(v, "as_tuple"):
        return round(float(v), 6)
    return v.isoformat() if hasattr(v, "isoformat") else v


def _is_json(s):
    try:
        json.loads(s)
        return True
    except ValueError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--new-version", action="store_true")
    args = ap.parse_args()

    data = {}
    for t, (reader, _v) in TABLES.items():
        cols, rows = reader()
        if not rows:
            sys.exit(f"{t}: the source file has no rows; nothing loaded")
        data[t] = (cols, rows)
        print(f"read   {t:<20} {len(rows):>3} rows")
    trunk = data["TRUNK_STEP"][1][0]
    print(f"trunk sizing from the sheet note: factor={trunk[2]} margin_ft={trunk[3]}" + ("" if trunk[2] and trunk[3] else "   <-- not stated in the note, left empty"))
    if args.dry_run:
        print("dry run: nothing changed")
        return

    import snowflake.connector
    con = snowflake.connector.connect(connection_name=os.environ.get("SNOWFLAKE_CONNECTION", "scopeiq"), database=DB, schema=SCHEMA, warehouse="SCOPEIQ_WH")
    cur = con.cursor()
    try:
        for t, (cols, rows) in data.items():
            versioned = TABLES[t][1]
            vcol = "VERSION" if versioned else None
            cur.execute(f"SELECT COUNT(*) FROM {DB}.{SCHEMA}.{t}")
            existing = cur.fetchone()[0]
            version = 1
            if existing:
                latest_where = ""
                if versioned:
                    cur.execute(f"SELECT MAX(VERSION) FROM {DB}.{SCHEMA}.{t}")
                    version = cur.fetchone()[0]
                    latest_where = f" WHERE VERSION = {version}"
                cur.execute(f"SELECT {', '.join(c for c in cols if c != 'VERSION')} FROM {DB}.{SCHEMA}.{t}{latest_where}")
                have = sorted(tuple(norm(x) for x in r) for r in cur.fetchall())
                src_cols = [c for c in cols if c != "VERSION"]
                src = sorted(tuple(norm(r[cols.index(c)]) for c in src_cols) for r in rows)
                if have == src:
                    print(f"same   {t:<20} already holds exactly this content (version {version})" if versioned else f"same   {t:<20} already holds exactly this content")
                    continue
                if not (versioned and args.new_version):
                    print(f"DIFFER {t:<20} holds different content ({len(have)} rows there, {len(src)} in the file); left as it is" + ("" if not versioned else "; use --new-version to add the file as version " + str(version + 1)))
                    continue
                cur.execute(f"UPDATE {DB}.{SCHEMA}.{t} SET EFFECTIVE_TO = %s WHERE VERSION = %s AND EFFECTIVE_TO IS NULL", (TODAY, version))
                version += 1
            ins_cols = list(cols) + ([] if (not versioned or "VERSION" in cols) else ["VERSION"])
            vi = ins_cols.index("VERSION") if "VERSION" in ins_cols else None
            prepared = []
            for r in rows:
                r = list(r) + ([version] if (versioned and "VERSION" not in cols) else [])
                if versioned and "VERSION" in cols:
                    r[vi] = version
                prepared.append(r)
            ph = ["PARSE_JSON(%s)" if c == "PARAMS_JSON" else "%s" for c in ins_cols]
            sql = f"INSERT INTO {DB}.{SCHEMA}.{t} ({', '.join(ins_cols)}) SELECT {', '.join(ph)}"
            for r in prepared:                      # row by row: the data is small, and INSERT ... SELECT cannot be batched
                cur.execute(sql, r)
            print(f"loaded {t:<20} {len(prepared):>3} rows" + (f" as version {version}" if versioned else ""))
        con.commit()
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    main()
