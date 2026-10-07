# ScopeIQ POC

ScopeIQ assists telecom site scoping across three streams: **Site Build BOM**, **Site Design** and **Network Deployment**.
It reads a site's RFDS, construction drawings, mount/structural analyses, drone capture and REV 0 BOM, and reconciles
them using a governing source per domain. From that it produces:

* the findings, each with evidence;
* redlines and RFIs;
* the corrected REV n BOM, with a reason for every change against REV 0;
* service drivers and an estimate.

People then take the work through review, the CX service-provider handshake and Final BOM Approval, in a mobile app
with mock persona logins.

On the ten sample sites it detects **all 22 seeded issues**, and its BOMs match the answer key (see `docs/TEST_RESULTS.md`).

| Start here | |
|---|---|
| Install and run | [INSTALL.md](INSTALL.md) |
| How it works | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Personas, workflow states and transitions | [docs/PERSONAS_AND_WORKFLOWS.md](docs/PERSONAS_AND_WORKFLOWS.md) |
| API endpoints | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) (or http://localhost:8000/docs) |
| Tables | [docs/DATA_MODEL.md](docs/DATA_MODEL.md) |
| Results and limitations | [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) |
| Snowflake deployment | [snowflake/EXECUTION_GUIDE.md](snowflake/EXECUTION_GUIDE.md) |

Quick start (Windows PowerShell):
```
cd code\backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1; python -m pip install -r requirements.txt
python scripts\run_pipeline.py            # all sites -> code\output
python -m uvicorn api.main:app --port 8000
# second terminal
cd code\mobile; npm install; npm run web  # sign in as scoper1
```

| Folder | Contents |
|---|---|
| `backend/scopeiq` | engine: extraction, reconciliation, design delta, BOM rules, revisions, estimate, redlines, workflow, database |
| `backend/api` | FastAPI, one router per area |
| `backend/scripts` | pipeline CLI, Snowflake SQL generator, docs generator, reference-data builder |
| `backend/tests` | acceptance tests against the answer key, unit tests and API tests |
| `reference_data` | rule and reference library (CSV, versioned and effective-dated) |
| `mobile` | React Native (Expo) app |
| `snowflake` | environment variables, numbered scripts, deploy script, execution guide |
| `output` | generated results, including the stored redlines for every sample site |
