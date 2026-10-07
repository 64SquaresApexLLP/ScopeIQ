"""Generate the reference documents that come straight from code and data (re-run after changing them):

    docs/PERSONAS_AND_WORKFLOWS.md   personas, demo users, workflow states and transitions (reference_data CSVs)
    docs/API_REFERENCE.md            every endpoint with roles, parameters and body (FastAPI OpenAPI)
    docs/openapi.json                machine-readable API description
    docs/DATA_MODEL.md               every table and column by layer (scopeiq/db/schema.py)
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SCOPEIQ__LOGGING__CONSOLE", "false")

CODE = Path(__file__).resolve().parents[2]
DOCS = CODE / "docs"
REF = CODE / "reference_data"


def rows(name: str) -> list[dict]:
    with open(REF / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def table(headers: list[str], data: list[list]) -> str:
    esc = lambda v: str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")  # noqa: E731
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)] + ["| " + " | ".join(esc(c) for c in r) + " |" for r in data]) + "\n"


def personas_doc() -> str:
    out = ["# Personas and workflows\n", "Generated from `reference_data/personas.csv`, `users.csv`, `workflow_states.csv` and "
           "`workflow_transitions.csv` by `backend/scripts/generate_docs.py`. The workflow engine reads the same rows at run time, "
           "so changing a CSV (and reloading reference data) changes the behaviour; no code change is needed.\n",
           "## Personas\n"]
    out.append(table(["Role", "Persona", "Organisation", "Goals", "Key screens", "Can approve", "Data scope", "Snowflake role"],
                     [[p["ROLE_CODE"], p["PERSONA_NAME"], p["ORGANISATION"], p["GOALS"], p["KEY_SCREENS"], p["CAN_APPROVE"], p["DATA_SCOPE"],
                       p["SNOWFLAKE_ROLE"]] for p in rows("personas.csv")]))
    out.append("\n## Demo users (mock login: pick a user, any non-empty password)\n")
    out.append(table(["User id", "Name", "Role", "Organisation", "Service provider"],
                     [[u["USER_ID"], u["DISPLAY_NAME"], u["ROLE_CODE"], u["ORGANISATION"], u["SERVICE_PROVIDER"]] for u in rows("users.csv")]))
    states = defaultdict(list)
    for s in rows("workflow_states.csv"):
        states[s["ENTITY_TYPE"]].append(s)
    trans = defaultdict(list)
    for t in rows("workflow_transitions.csv"):
        trans[t["ENTITY_TYPE"]].append(t)
    out.append("\n## Workflow tracking\n\nEvery transition writes `WF.WORKFLOW_EVENT` (from, action, to, actor, role, reason, comment, "
               "correlation id), an `AUDIT.AUDIT_LOG` row, and inbox notifications (`WF.NOTIFICATION`) for the roles listed. "
               "`*` as a from-state means the action is allowed from any state. A locked state makes the record immutable "
               "(for example an approved BOM revision: further changes need a new revision).\n")
    for ent in states:
        out.append(f"\n### {ent}\n\nStates\n\n")
        out.append(table(["Seq", "State", "Initial", "Terminal", "Locked", "Owner", "Meaning"],
                         [[s["SEQ"], s["STATE"], s["IS_INITIAL"], s["IS_TERMINAL"], s["IS_LOCKED"], s["OWNER_ROLE"], s["DESCRIPTION"]] for s in states[ent]]))
        out.append("\nTransitions\n\n")
        out.append(table(["From", "Action", "To", "Allowed roles", "Reason code", "Comment", "Notifies", "Meaning"],
                         [[t["FROM_STATE"], t["ACTION"], t["TO_STATE"], t["ALLOWED_ROLES"].replace(";", ", "), t["REQUIRES_REASON"],
                           t["REQUIRES_COMMENT"], t["NOTIFY_ROLES"].replace(";", ", "), t["DESCRIPTION"]] for t in trans[ent]]))
        out.append("\n```mermaid\nstateDiagram-v2\n" + "".join(
            f"    {t['FROM_STATE'] if t['FROM_STATE'] != '*' else '[*]'} --> {t['TO_STATE']}: {t['ACTION']}\n" for t in trans[ent]) + "```\n")
    out.append("\n## Reason codes\n\n")
    out.append(table(["Code", "Category", "Description", "Fault party", "Applies to"],
                     [[r["REASON_CODE"], r["CATEGORY"], r["DESCRIPTION"], r["FAULT_PARTY"], r["APPLIES_TO"].replace(";", ", ")] for r in rows("reason_codes.csv")]))
    return "".join(out)


def api_doc() -> tuple[str, dict]:
    from api.main import app
    spec = app.openapi()
    out = ["# API reference\n", "Generated from the FastAPI application by `backend/scripts/generate_docs.py` "
           "(interactive version at `http://localhost:8000/docs` while the API runs).\n",
           "\nAuthentication: `POST /auth/login` with `{\"user_id\": \"scoper1\", \"password\": \"demo\"}` returns a token; send "
           "`Authorization: Bearer <token>` on every other call (file downloads also accept `?access_token=`). Roles are enforced "
           "per endpoint and, for workflow actions, by the workflow tables (see PERSONAS_AND_WORKFLOWS.md).\n",
           "\nErrors always use one envelope: `{\"error\": {\"code\": \"SIQ-NF-404\", \"message\": \"...\", \"correlation_id\": \"...\", "
           "\"details\": {...}}}`. Codes: SIQ-VAL-400 invalid input, SIQ-AUTH-401 not signed in, SIQ-AUTH-403 role not allowed, "
           "SIQ-NF-404 not found, SIQ-CONF-409 / SIQ-WF-409 / SIQ-LOCK-409 conflict, workflow or locked record, SIQ-EXT-422 document "
           "unreadable, SIQ-DB-503 database unavailable, SIQ-SYS-500 unexpected. Every response carries `X-Correlation-ID`.\n"]
    by_tag = defaultdict(list)
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            by_tag[(op.get("tags") or ["other"])[0]].append((path, method.upper(), op))
    schemas = spec.get("components", {}).get("schemas", {})
    for tag, ops in by_tag.items():
        out.append(f"\n## {tag}\n")
        for path, method, op in ops:
            out.append(f"\n### `{method} {path}`\n\n")
            doc = (op.get("description") or op.get("summary") or "").strip()
            if doc:
                out.append(doc.split("\n\n")[0] + "\n\n")
            params = [p for p in op.get("parameters", []) if p["name"] not in ("authorization",)]
            if params:
                out.append(table(["Parameter", "In", "Required", "Type"],
                                 [[p["name"], p["in"], "yes" if p.get("required") else "no",
                                   p.get("schema", {}).get("type") or "/".join(x.get("type", "") for x in p.get("schema", {}).get("anyOf", []))] for p in params]))
            body = op.get("requestBody", {}).get("content", {})
            for ct, c in body.items():
                ref = c.get("schema", {}).get("$ref", "")
                name = ref.split("/")[-1]
                if name in schemas:
                    props = schemas[name].get("properties", {})
                    req = set(schemas[name].get("required", []))
                    out.append(f"\nBody (`{ct}`, {name}):\n\n")
                    out.append(table(["Field", "Required", "Type"], [[k, "yes" if k in req else "no",
                                     v.get("type") or "/".join(x.get("type", "") for x in v.get("anyOf", []))] for k, v in props.items()]))
    return "".join(out), spec


def data_model_doc() -> str:
    from scopeiq.db.schema import LAYERS, tables
    names = {"S": "text", "N": "decimal", "I": "integer", "B": "boolean", "T": "timestamp", "D": "date", "V": "JSON / VARIANT"}
    out = ["# Data model\n", "Generated from `scopeiq/db/schema.py`, the single schema registry used for both SQLite (local) and "
           "Snowflake (`snowflake/03_tables.sql`).\n"]
    for lyr in LAYERS:
        out.append(f"\n## {lyr}\n")
        for t in tables(lyr):
            out.append(f"\n### {t.fqn}\n\n{t.comment}\n\n")
            out.append(table(["Column", "Type", "Key"], [[c.name, names[c.type], "PK" if c.pk else ("not null" if c.not_null else "")] for c in t.columns]))
    return "".join(out)


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "PERSONAS_AND_WORKFLOWS.md").write_text(personas_doc(), encoding="utf-8")
    api_md, spec = api_doc()
    (DOCS / "API_REFERENCE.md").write_text(api_md, encoding="utf-8")
    (DOCS / "openapi.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    (DOCS / "DATA_MODEL.md").write_text(data_model_doc(), encoding="utf-8")
    print("wrote docs/PERSONAS_AND_WORKFLOWS.md, API_REFERENCE.md, openapi.json, DATA_MODEL.md")


if __name__ == "__main__":
    main()
