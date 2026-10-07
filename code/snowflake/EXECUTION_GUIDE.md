# ScopeIQ on Snowflake: execution guide

This guide takes an empty Snowflake account to a working ScopeIQ environment: data staged, tables created,
reference data loaded, the pipeline running as a stored procedure (or a container job), results visible to the
API and the mobile app, and logging set per environment.

It revises `Data/DataDetails/snowflake_load.sql`, which created one stage, a file registry view and four
SiteTracker tables. The scripts here keep that design and add:

| Change | Why |
|---|---|
| Stage paths mirror `ScopeIQ-POC/Data` (`Input-Data/Sites/<SITE>/...`) | local runs and Snowflake runs read the same paths |
| `uploads/<SITE>/<folder>/` area on the stage | documents uploaded from the app take part in revision resolution |
| `FILE_REGISTRY` classifies document type and revision | same rules as `scopeiq/extract/registry.py` |
| SiteTracker tables with fixed columns (schema registry) instead of `INFER_SCHEMA` | stable types, no drift between environments |
| REF, CORE, WF, AUDIT schemas generated from `scopeiq/db/schema.py` | one schema definition for SQLite and Snowflake |
| Snowpark procedure, stream and tasks | pipeline re-runs when a site's documents change |
| Per-environment variables, log level and retention | Dev verbose, Test traceable, Prod minimal, without code changes |

## 1. What gets created

| Object | Name (dev) | Purpose |
|---|---|---|
| Roles | `SCOPEIQ_DEV_ADMIN`, `SCOPEIQ_DEV_APP`, `SCOPEIQ_DEV_READ` | owner / application / reporting |
| Warehouse | `SCOPEIQ_DEV_WH` | XSMALL, auto-suspend 60 s |
| Database | `SCOPEIQ_DEV` | schemas below |
| `RAW` | stages `SITE_DOCS`, `SCOPEIQ_CODE`, `SCOPEIQ_OUTPUT`, `SEED`; `ST_*` tables; `FILE_REGISTRY`; `DOC_PARSE` | landing |
| `REF` | 13 tables (catalog, kit rules, trunk steps, consistency rules, drivers, rate card, requirements, cycle-time, reason codes, personas, users, workflow states and transitions) | business rules as data |
| `CORE` | SITE, DOCUMENT, DISCREPANCY, BOM_REVISION, BOM_LINE, BOM_CHANGE, REDLINE, RFI, ESTIMATE ... | pipeline results and business records |
| `WF` | WORKFLOW_EVENT, NOTIFICATION, COMMENT | workflow tracking |
| `AUDIT` | AUDIT_LOG, APP_LOG, ERROR_LOG, event table SCOPEIQ_EVENTS | audit and logs |
| `APP` | SETTINGS, procedures, tasks, reporting views | operations |

Test and prod use the same names with `TEST` / `PROD` (see `config/env_<env>.sql`).

## 2. Files

| File | Run as | What it does |
|---|---|---|
| `config/env_dev.sql`, `env_test.sql`, `env_prod.sql` | (prefix) | session variables: names, sizes, log levels, task schedule |
| `01_account_setup.sql` | ACCOUNTADMIN | roles, warehouse, database, schemas, grants, LOG_LEVEL |
| `02_stages_and_formats.sql` | admin role | stages, file formats, `FILE_REGISTRY`, stage stream |
| `03_tables.sql` | admin role | all tables (generated) |
| `04_load_sitetracker.sql` | admin role | COPY SiteTracker CSVs into `RAW.ST_*` (generated) |
| `05_load_reference.sql` | admin role | COPY reference CSVs into `REF.*` (generated) |
| `06_build_core_sites.sql` | admin role | MERGE sites and milestones into CORE |
| `07_procedures.sql` | admin + ACCOUNTADMIN for one grant | `APP.SETTINGS`, `SP_RUN_PIPELINE`, `SP_RUN_CHANGED_SITES` |
| `08_ai_parse_documents.sql` | admin role | `AI_PARSE_DOCUMENT` on staged PDFs into `RAW.DOC_PARSE` |
| `09_tasks.sql` | admin + ACCOUNTADMIN for EXECUTE TASK | pipeline task on stream, PDF parse task, log purge |
| `10_views.sql` | admin role | reporting views in APP |
| `11_load_pipeline_results.sql` | admin role | load results exported from a local run (generated) |
| `12_logging_and_monitoring.sql` | admin + ACCOUNTADMIN for event table | event table, log views, optional alert |
| `99_teardown.sql` | ACCOUNTADMIN | drops one environment (guarded) |
| `deploy_snowflake.py` | | runs the above in order and uploads files |
| `seed/*.json` | | pipeline results from the local run (generated) |
| `spcs/pipeline_job.yaml` | | container job spec for OCR-capable runs |

Files marked "generated" are written by `backend/scripts/generate_snowflake_sql.py` from the schema registry.
Regenerate them after changing `scopeiq/db/schema.py` or a reference CSV header; never edit them by hand.

## 3. Prerequisites

1. A Snowflake account and a user with ACCOUNTADMIN (for the one-time setup) in a region where Cortex
   `AI_PARSE_DOCUMENT` is available (only needed for step 08).
2. Python 3.11+ with the backend requirements and the Snowflake extras:
   ```
   cd ScopeIQ-POC\code\backend
   python -m pip install -r requirements-snowflake.txt
   ```
3. Optional: the Snowflake CLI (`pip install snowflake-cli`) if you prefer running scripts by hand.
4. The local pipeline has run at least once (`python scripts/run_pipeline.py`) if you want step 11 to
   pre-load results. The repository already contains that run's output.

## 4. Generate the schema-driven files

```
cd ScopeIQ-POC\code\backend
python scripts\generate_snowflake_sql.py
```
Expected output:
```
wrote 03_tables.sql, 04_load_sitetracker.sql, 05_load_reference.sql
exported about 6,500 rows from 26 tables to snowflake/seed/
packaged ...\code\dist\scopeiq_code.zip
```

## 5. Deploy (recommended: the deploy script)

Set the connection once per terminal.

PowerShell:
```
$env:SNOWFLAKE_ACCOUNT = "<orgname>-<account>"
$env:SNOWFLAKE_USER = "<you>"
$env:SNOWFLAKE_AUTHENTICATOR = "externalbrowser"     # or $env:SNOWFLAKE_PASSWORD = "..."
```
Command Prompt uses `set NAME=value`; macOS/Linux use `export NAME=value`.

Then:
```
cd ScopeIQ-POC\code\snowflake
python deploy_snowflake.py --env dev --dry-run --all     # check the plan
python deploy_snowflake.py --env dev --all
```
`--all` runs 01 through 12. Between 02 and 03 it uploads:

| Local folder | Stage path |
|---|---|
| `Data/Input-Data` | `@RAW.SITE_DOCS/Input-Data` |
| `Data/Reference-Data` | `@RAW.SITE_DOCS/Reference-Data` |
| `code/reference_data` | `@RAW.SCOPEIQ_CODE/reference_data` |
| `code/dist/scopeiq_code.zip` | `@RAW.SCOPEIQ_CODE` |
| `code/snowflake/seed` | `@RAW.SEED` |

Re-run selected steps with `--steps`, for example after editing a reference CSV:
```
python deploy_snowflake.py --env dev --upload --steps 05
```

## 6. Deploy by hand (worksheet or Snowflake CLI)

Each script expects the variables, so run the environment file first **in the same session**:

* Snowsight worksheet: paste `config/env_dev.sql` above the script and run all.
* Snowflake CLI: `type config\env_dev.sql 01_account_setup.sql > run.sql` then `snow sql -f run.sql`
  (macOS/Linux: `cat config/env_dev.sql 01_account_setup.sql > run.sql`).

Uploads with the CLI (from `ScopeIQ-POC`):
```
snow stage copy "Data/Input-Data"     @SCOPEIQ_DEV.RAW.SITE_DOCS/Input-Data --recursive
snow stage copy "Data/Reference-Data" @SCOPEIQ_DEV.RAW.SITE_DOCS/Reference-Data --recursive
snow stage copy code/reference_data   @SCOPEIQ_DEV.RAW.SCOPEIQ_CODE/reference_data --recursive
snow stage copy code/dist/scopeiq_code.zip @SCOPEIQ_DEV.RAW.SCOPEIQ_CODE
snow stage copy code/snowflake/seed   @SCOPEIQ_DEV.RAW.SEED --recursive
```
`PUT` and `snow stage copy` do not work from a Snowsight worksheet; use the Snowsight stage upload page
instead if you have no CLI.

## 7. Step by step: what to check

| Step | Check | Expected |
|---|---|---|
| 01 | `SHOW SCHEMAS IN DATABASE SCOPEIQ_DEV;` | RAW, REF, CORE, WF, AUDIT, APP |
| 02 | `SELECT AREA, DOC_TYPE, COUNT(*) FROM RAW.FILE_REGISTRY GROUP BY 1,2;` | SITE rows for RFDS, CD, MA_SA, BOM_REV0, DRONE_*; 4 SITETRACKER rows |
| 03 | `SELECT TABLE_SCHEMA, COUNT(*) FROM INFORMATION_SCHEMA.TABLES GROUP BY 1;` | REF 13, CORE 24, WF 3, AUDIT 3, RAW 4 (plus RAW.DOC_PARSE after 08, APP tables after 07) |
| 04 | last statement of the script | ST_SITE 10, ST_PROJECT 10, ST_MILESTONE 100, ST_DOCUMENT 133 |
| 05 | last statement | every REF table with rows |
| 06 | last statement | 10 sites, state ASSIGNED, stream and CX SP filled |
| 07 | `CALL APP.SP_RUN_PIPELINE('TXDA1024', CURRENT_USER());` | `{"sites":[{"site_id":"TXDA1024","status":"SUCCEEDED",...}]}` |
| 08 | `SELECT COUNT(*) FROM RAW.DOC_PARSE;` | one row per staged PDF |
| 09 | `SHOW TASKS IN SCHEMA APP;` | three tasks, state started |
| 10 | `SELECT * FROM APP.V_SITE_STATUS;` | one row per site with open discrepancies and estimate |
| 11 | last statement | discrepancy, redline and BOM line counts matching the local run |
| 12 | `SELECT * FROM APP.V_PROCEDURE_LOGS ORDER BY TIMESTAMP DESC LIMIT 20;` | log lines from the procedure call |

### Running the pipeline

* One site: `CALL APP.SP_RUN_PIPELINE('TXIR1340', CURRENT_USER());`
* Several: `CALL APP.SP_RUN_PIPELINE('TXIR1340,TXMK1112', CURRENT_USER());`
* All staged sites: `CALL APP.SP_RUN_PIPELINE('', CURRENT_USER());`
* Automatically: upload a corrected document to `@RAW.SITE_DOCS/uploads/<SITE>/cds/` (or replace a file under
  `Input-Data/Sites/<SITE>/`). The stream picks it up and `APP.T_RUN_CHANGED_SITES` runs the pipeline on its
  schedule. `EXECUTE TASK APP.T_RUN_CHANGED_SITES;` runs it now.

Generated files (BOM workbook, redlined CD PDF, discrepancy/redline/RFI packages, evidence frames) are written to
`@RAW.SCOPEIQ_OUTPUT/sites/<SITE>/` and `@RAW.SCOPEIQ_OUTPUT/evidence/<SITE>/`:
```
LIST @RAW.SCOPEIQ_OUTPUT/sites/TXDA1024/;
```

### Known limits of the stored procedure, and the container alternative

* **Scanned CDs (PDF only, no DXF).** A warehouse has no Tesseract, so the procedure runs with OCR disabled. For
  such sites the CD is reported as unreadable (EXT warning) and the reviewer uses `RAW.V_DOC_PARSE_PAGES` (step 08).
  For full fidelity run the pipeline as a Snowpark Container Services job, which has Tesseract:
  1. Create an image repository and a compute pool (`CREATE IMAGE REPOSITORY APP.IMAGES;`,
     `CREATE COMPUTE POOL SCOPEIQ_POOL MIN_NODES=1 MAX_NODES=1 INSTANCE_FAMILY=CPU_X64_S;`).
  2. From `code/`: `docker build -f backend/Dockerfile -t <repository_url>/scopeiq:latest .` and push it.
  3. Upload `spcs/pipeline_job.yaml` to `@RAW.SCOPEIQ_CODE` and run
     `EXECUTE JOB SERVICE IN COMPUTE POOL SCOPEIQ_POOL NAME = APP.SCOPEIQ_PIPELINE_JOB FROM @RAW.SCOPEIQ_CODE SPECIFICATION_FILE = 'pipeline_job.yaml';`
* **Python packages.** `SP_RUN_PIPELINE` takes `ezdxf`, `laspy`, `opencv-python-headless` and `pymupdf` from
  PyPI through `snowflake.snowpark.pypi_shared_repository`. If your account does not allow the PyPI repository,
  use the container job above.
* **Not run against a live account.** The scripts were syntax-checked with sqlglot (Snowflake dialect,
  277 statements, 0 failures) and the procedure entry point was written against the Snowpark API, but they have
  not been executed on a Snowflake account from this POC environment. Expect to adjust account-specific items
  (region availability of Cortex, PyPI repository access, role names) on first deployment.

## 8. Logging per environment

Two independent controls, neither requires a code change.

| Setting | Dev | Test | Prod | Where |
|---|---|---|---|---|
| ScopeIQ logger level | DEBUG | INFO | WARNING (pipeline, access and audit loggers at INFO) | `scopeiq/config/<env>.yaml`, `APP.SETTINGS.APP_LOG_LEVEL` |
| Request/response payloads | on | off | off | `logging.log_payloads` |
| SQL statements with timings | on | on | off | `logging.log_sql` |
| PII masking in log lines | off | on | on | `logging.mask_pii` |
| Rows written to `AUDIT.APP_LOG` | INFO+ | INFO+ | WARNING+ | `logging.db_sink_level` |
| Snowflake LOG_LEVEL (event table) | DEBUG | INFO | WARN | `config/env_<env>.sql` |
| `AUDIT.APP_LOG` retention | 14 days | 30 days | 90 days | `APP.SETTINGS.APP_LOG_RETENTION_DAYS` |

`AUDIT.AUDIT_LOG` (who changed what, why) and `WF.WORKFLOW_EVENT` are never purged. Errors always go to
`AUDIT.ERROR_LOG` with the stack trace and the correlation id the API returned to the user.

Change at run time:
```
UPDATE APP.SETTINGS SET VALUE = 'DEBUG' WHERE KEY = 'APP_LOG_LEVEL';
ALTER PROCEDURE APP.SP_RUN_PIPELINE(VARCHAR, VARCHAR) SET LOG_LEVEL = 'DEBUG';
```
For the API, set `SCOPEIQ_ENV=prod` and override any single key with an environment variable, for example
`SCOPEIQ__LOGGING__LEVEL=INFO`.

## 9. Pointing the API at Snowflake

In `code/backend/scopeiq/config/<env>.yaml` (or environment variables):
```
database:
  backend: snowflake
  snowflake:
    account: <orgname>-<account>
    user: SCOPEIQ_SVC
    authenticator: snowflake_jwt
    private_key_path: C:\keys\scopeiq_svc.p8
    role: SCOPEIQ_DEV_APP
    warehouse: SCOPEIQ_DEV_WH
    database: SCOPEIQ_DEV
reference:
  source: database
```
Create the service user once:
```
CREATE USER SCOPEIQ_SVC TYPE = SERVICE DEFAULT_ROLE = SCOPEIQ_DEV_APP RSA_PUBLIC_KEY = '<public key>';
GRANT ROLE SCOPEIQ_DEV_APP TO USER SCOPEIQ_SVC;
```
Then `uvicorn api.main:app` serves the same endpoints from Snowflake. `python scripts/run_pipeline.py --backend snowflake`
runs the pipeline locally (with OCR) and writes to Snowflake.

## 10. Promoting dev to test and prod

1. `python deploy_snowflake.py --env test --all` (separate database, warehouse and roles).
2. Do not run step 11 in prod unless you want the POC results there; run the pipeline instead.
3. Reference data changes: edit the CSV (new VERSION and EFFECTIVE_FROM rows rather than editing old rows),
   commit, then `python deploy_snowflake.py --env <env> --upload --steps 05`.
4. Code changes: regenerate the zip (`generate_snowflake_sql.py`), upload, then re-run step 07.
5. Zero-copy clone for a quick test copy: `CREATE DATABASE SCOPEIQ_TEST CLONE SCOPEIQ_DEV;`

## 11. Teardown

```
SET CONFIRM_TEARDOWN = 'SCOPEIQ_DEV';
-- with config/env_dev.sql loaded in the same session:
-- run 99_teardown.sql
```
This drops the database, warehouse and roles of that environment. It cannot be undone except through Time Travel
on the dropped database (`UNDROP DATABASE SCOPEIQ_DEV;` within the retention period).

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Session variable '$SCOPEIQ_DB' does not exist` | env file not run in the same session | prepend `config/env_<env>.sql` |
| `FILE_REGISTRY` empty | stage not refreshed | `ALTER STAGE RAW.SITE_DOCS REFRESH;` |
| COPY into `REF.*` fails on column count | CSV header changed | regenerate with `generate_snowflake_sql.py`, re-run 03 (new columns) and 05 |
| `SP_RUN_PIPELINE` fails with `No module named ...` | PyPI repository not granted | `GRANT DATABASE ROLE SNOWFLAKE.PYPI_REPOSITORY_USER TO ROLE SCOPEIQ_DEV_ADMIN;` or use the container job |
| Site shows CD unreadable in Snowflake but not locally | scanned CD needs OCR | container job (section 7) |
| API returns `SIQ-DB-503` | connection settings | check `database.snowflake.*`, then `AUDIT.ERROR_LOG` by correlation id |
