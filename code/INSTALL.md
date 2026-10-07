# ScopeIQ POC: installation and first run

This guide sets up the ScopeIQ POC on a Windows laptop. macOS and Linux commands follow where they differ.
You end with:

* the pipeline run on the ten sample sites;
* the API on `http://localhost:8000`;
* the app open in a browser, and optionally on a phone through Expo Go.

Snowflake is optional and is covered in `snowflake/EXECUTION_GUIDE.md`.

Folder layout (all paths below are relative to `ScopeIQ-POC`):

```
ScopeIQ-POC/
  Data/                     input documents (read only: Sites, SiteTracker, Reference-Data, DataDetails)
  code/
    backend/                Python: scopeiq package (engine), api (FastAPI), scripts, tests
    reference_data/         business rules and reference data as CSV (catalog, kit rules, workflow, personas ...)
    mobile/                 React Native (Expo) app
    snowflake/              Snowflake scripts, deploy script, execution guide
    docs/                   architecture, personas/workflows, API reference, data model, test results
    output/                 generated: local database, BOM workbooks, redlined CDs, evidence frames, logs
    dist/                   generated: scopeiq_code.zip for the Snowflake procedures
```

## 1. Prerequisites

| Tool | Version | Needed for | Windows install |
|---|---|---|---|
| Python | 3.11 or newer | pipeline and API | https://www.python.org/downloads/ (tick "Add python.exe to PATH") |
| Tesseract OCR | 5.x | reading the two scanned CDs (PDF only) | UB Mannheim installer: https://github.com/UB-Mannheim/tesseract/wiki |
| Node.js | 20 LTS or newer | mobile app | https://nodejs.org |
| Git (optional) | any | version control | https://git-scm.com |
| Expo Go (optional) | latest | running the app on a phone | App Store / Google Play |

On macOS, run `brew install python@3.12 tesseract node`. On Ubuntu, run `sudo apt install python3 python3-venv tesseract-ocr nodejs npm`.

Check:
```
python --version
tesseract --version
node --version
```
If `tesseract` is not found on Windows, it is installed but not on PATH. Either add `C:\Program Files\Tesseract-OCR` to PATH,
or set the path in `code/backend/.env` (step 3):
```
SCOPEIQ__ENGINE__TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
```
Without Tesseract everything still runs. The two sites whose CD exists only as a scanned PDF (TXAD0405, TXIR1340) then
report the CD as unreadable instead of reading it.

## 2. Python environment

PowerShell, from `ScopeIQ-POC\code\backend`:
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
On macOS or Linux, activate with `source .venv/bin/activate`.

For Snowflake as the database, also install the Snowflake extras: `python -m pip install -r requirements-snowflake.txt`.

## 3. Configuration (environment, logging, database)

All settings live outside the code:

| Layer | File / variable | Purpose |
|---|---|---|
| Base | `backend/scopeiq/config/base.yaml` | paths, engine tolerances, API, database |
| Environment | `backend/scopeiq/config/dev.yaml`, `test.yaml`, `prod.yaml` | logging level and detail per environment, database name |
| Selection | `SCOPEIQ_ENV=dev` (default), `test` or `prod` | which environment file applies |
| Override | `SCOPEIQ__<SECTION>__<KEY>=value` | any single key, e.g. `SCOPEIQ__LOGGING__LEVEL=INFO` |
| Local file | `backend/.env` (copy `backend/.env.example`) | the same variables, read at start-up; real environment variables win |

Logging per environment:

| | dev | test | prod |
|---|---|---|---|
| Level | DEBUG | INFO | WARNING (pipeline, request and audit summaries at INFO) |
| Format | readable text | JSON | JSON |
| Request/response bodies | logged | no | no |
| SQL with timings | logged | logged | no |
| Names/emails masked | no | yes | yes |
| Written to `AUDIT.APP_LOG` | INFO+ | INFO+ | WARNING+ |

Errors always go to `AUDIT.ERROR_LOG` with the stack trace and a correlation id. That id is also returned to the user
in every error response and shown in the app. Log files rotate in `code/output/logs/`.

To switch environment for one PowerShell session, run `$env:SCOPEIQ_ENV = "prod"` (in Command Prompt, `set SCOPEIQ_ENV=prod`).

## 4. Run the pipeline

From `code\backend` with the virtual environment active:
```
python scripts\run_pipeline.py                 # all ten sites (the OCR sites take the longest)
python scripts\run_pipeline.py TXDA1024        # one site
```
The run prints one line per site with the number of findings, the BOM revision, redlines, RFIs and warnings. Results go to:

* `code/output/scopeiq_local.db`: the SQLite database, with the same tables as Snowflake;
* `code/output/sites/<SITE>/`: the REV 1 BOM workbook;
* `code/output/sites/<SITE>/redlines/`: the red-marked CD PDF, plus discrepancies, redlines and RFIs as JSON and CSV;
* `code/output/evidence/<SITE>/`: drone video frames.

The repository already contains the output of a full run, so the app has data even before you run anything.

Re-running is safe. Human decisions on findings, redlines and RFIs (status, reason, assignee) are kept. A REV 1 that
is still a DRAFT is refreshed in place. An approved revision is never changed; the run creates the next revision instead.

## 5. Run the tests

```
python -m pytest
```
The expected result is `19 passed`. `docs/TEST_RESULTS.md` explains what each test checks.

## 6. Start the API

```
python -m uvicorn api.main:app --reload --port 8000
```
* Health check: http://localhost:8000/health
* Interactive API documentation: http://localhost:8000/docs
* Sign in through the API: `POST /auth/login` with `{"user_id": "scoper1", "password": "demo"}`.

To let a phone reach the API, start it on all interfaces with `--host 0.0.0.0`. Windows Firewall will ask to allow
Python on private networks; allow it.

## 7. Run the mobile app

From `code\mobile`:
```
npm install
npm run web                 # opens the app in the browser (dev environment)
```
App environments are also chosen outside the code:

| Command | Config file | API |
|---|---|---|
| `npm start` / `npm run web` | `mobile/config/dev.json` | http://localhost:8000, debug logging, environment banner |
| `$env:APP_ENV="test"; npx expo start` | `mobile/config/test.json` | info logging |
| `$env:APP_ENV="prod"; npx expo start` | `mobile/config/prod.json` | warnings only, no banner |
| any, plus `$env:SCOPEIQ_API_URL="http://192.168.1.20:8000"` | | overrides the API address |

On a phone:
1. Find your PC's IP address: `ipconfig`, then the IPv4 address of your Wi-Fi adapter.
2. Start the API with `--host 0.0.0.0` (step 6).
3. In `code\mobile`:
   ```
   $env:SCOPEIQ_API_URL = "http://<your-ip>:8000"
   npx expo start
   ```
4. Scan the QR code with Expo Go. The phone and the PC must be on the same network.

The app forwards its own warnings and errors to the API (`POST /logs/client`), at the level set by `remoteLogLevel`.

### Demo logins

Pick a persona on the login screen. There is no password; the mock login accepts any.

| User | Persona | Sees / does |
|---|---|---|
| scoper1, scoper2 | Scoping engineer | all market sites; confirms or dismisses findings, drafts redlines and RFIs, edits the DRAFT BOM, uploads documents |
| reviewer1 | Scoping lead / QA | approval queue; approves and locks BOMs, approves redlines, sends BOMs to the SP |
| sp_prairie, sp_brazos, sp_redline | CX service provider | only its own sites; agrees or requests changes on the BOM in the handshake |
| ericsson1 | Ericsson scoping lead | answers RFIs, gives Final BOM Approval |
| ae1 | A&E engineer | receives redlines, acknowledges, uploads corrected drawings |
| ehs1 | EH&S manager | acknowledges and mitigates safety alerts |
| admin | Administrator | everything, plus logs, configuration and reference data reload |

`docs/PERSONAS_AND_WORKFLOWS.md` lists every state, transition, role and reason code.

## 8. A five-minute walkthrough

1. Sign in as **scoper1**. The dashboard shows ten sites, the open findings and the estimate.
2. **Sites > TXGR0719 > Discrepancies.** RFC-02 (the RFDS adds Radio 4460, which the CD omits) and FLD-06 (the
   field route is 80 ft against 40 ft on the CD) each show what was expected, what was found, and which document
   governs. Confirm one, then choose *Raise RFI* or *Create redline*.
3. **BOM > REV 1.** The lines are grouped by sector, and every line shows the rule that produced it. *Changes vs REV 0*
   shows each change with its reason code. Edit a quantity; a reason code is required. Then *Submit review*.
4. Sign out and sign in as **reviewer1**. Approve the BOM from the work queue. The revision is now locked, and an edit returns
   "cannot be edited - create a new revision".
5. **Redlines & RFIs > Open red-marked CD (PDF)** opens the stored redline for the site.
6. **Documents > Upload a document** (scoper or A&E) accepts a corrected CD such as `TXGR0719_CD_REV2.pdf`.
   *Run pipeline now* registers it as the current revision and re-checks the site.
7. As **admin**, **More > Logs and configuration** shows the error log, the application log and the active settings.

## 9. Regenerating generated files

| After changing | Run (from `code/backend`) |
|---|---|
| a table in `scopeiq/db/schema.py` or a reference CSV header | `python scripts/generate_snowflake_sql.py` |
| the API, a persona, a workflow CSV or the schema | `python scripts/generate_docs.py` |
| `Data/Reference-Data/*.xlsx` (catalog / BOM rules workbooks) | `python scripts/build_reference_data.py` |

The local SQLite database creates its tables automatically. To start from a clean database, delete
`code/output/scopeiq_local.db` and run the pipeline again.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | activate the virtual environment (`.\.venv\Scripts\Activate.ps1`) |
| `Tesseract OCR is not installed` warning for TXAD0405 / TXIR1340 | install Tesseract or set `SCOPEIQ__ENGINE__TESSERACT_CMD` |
| App shows "Cannot reach the ScopeIQ API" | API not running, or a phone is using `localhost`; set `SCOPEIQ_API_URL` to the PC's IP and start the API with `--host 0.0.0.0` |
| `database is locked` | another process (e.g. a DB browser) holds `scopeiq_local.db` open; close it |
| Port 8000 in use | `python -m uvicorn api.main:app --port 8010` and `SCOPEIQ_API_URL=http://localhost:8010` |
| Any error in the app | note the `ref` id shown; as admin, look it up under More > Logs (or `AUDIT.ERROR_LOG`) |
