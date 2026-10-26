# SharePoint integration

Site documents live in a SharePoint document library, one folder per site. An admin creates a site (which creates its folder),
and users upload files into the folder of the site they select.

```
<library_root>/<SITE_ID>/rfds | cds | ma_sa | bom | drone | drone/imagery | drone/video
```

## What a user sees

| Screen | Who | What it does |
|---|---|---|
| **Admin** tab | ADMIN only | Create a site: id (4 letters + 4 digits, e.g. `TXDA1024`), name, city, state, stream, structure, height. Creates the SharePoint folder tree and the site record. |
| **SharePoint** tab | SCOPER, A&E, CX SP, Ericsson (and admin) | 1. select a site, 2. choose files, 3. upload. With no site selected the screen shows **"Please select one site"** and the upload controls are hidden. Shows the files already in the selected site's folder. |

## Rules enforced by the API (not just the screen)

* The site comes from the URL (`POST /sharepoint/sites/{site_id}/upload`), so a file can only be written to that one site's folder.
* The site must already have a folder (`404` otherwise). Only an admin creates sites (`POST /admin/sites`, `403` for others, `409` if it exists).
* A file named for another site is rejected (`'TXDA1024_CD_REV1.pdf' is named for site TXDA1024, but TXPL0588 is selected`).
* The document type is detected from the file name with the same convention the pipeline uses (`TXDA1024_CD_REV2.pdf`, `TXDA1024_RFDS_R4.xlsx`, ...) and decides the sub-folder. If it cannot be told, the upload is refused with a hint; the user can pick the type explicitly.
* Empty files, files over `sharepoint.max_upload_mb` (400) and unsafe names / paths are refused.
* Identical content already in the site is **flagged** (`duplicate_of`), not blocked; the pipeline's duplicate rule (DOC-02) handles it later.
* Every site creation and upload is written to the audit trail.

## API

| Method and path | Role | Purpose |
|---|---|---|
| `GET /sharepoint/status` | any | provider, library location, document types |
| `GET /sharepoint/sites` | any (CX SP sees own sites only) | sites that have a folder, with file counts |
| `POST /admin/sites` | ADMIN | create site + folder |
| `GET /sharepoint/sites/{site_id}/files` | any | files in the site folder |
| `POST /sharepoint/sites/{site_id}/upload` | SCOPER, AE_ENGINEER, CX_SP, ERICSSON, ADMIN | multipart `file` (+ optional `doc_type`) |

## Providers (`sharepoint.provider`)

* **`local`** (default): a folder on disk, `output/sharepoint/<library_root>/...`, standing in for the library. Works offline; used for the demo and the tests.
* **`graph`**: the real SharePoint through Microsoft Graph. Needs an Entra ID app registration with the application permission
  `Sites.Selected` (preferred, granted on the one site) or `Sites.ReadWrite.All`, plus admin consent. Settings (see `.env.example`):
  `SCOPEIQ__SHAREPOINT__PROVIDER=graph`, `...GRAPH__TENANT_ID`, `...CLIENT_ID`, `...CLIENT_SECRET`, `...SITE_HOSTNAME`, `...SITE_PATH`, `...DRIVE_NAME`.
  Keep the secret in `backend/.env` (git-ignored), never in `base.yaml`.
  **Status:** written against the Graph documentation and covered by request-shape tests with a mock transport. It has **not** been run against a live tenant yet.

## Not built yet

* The pipeline still reads its inputs from `paths.sites_dir`, not from SharePoint. Connecting them (sync a site's SharePoint folder to the pipeline's input folder, then run) is the next step.
* New-file notifications (Inbox) and auto-starting the pipeline on upload.
* Deleting or renaming files and sites.

## Tests

`backend/tests/test_sharepoint.py` (9 tests): admin-only site creation, folder tree, upload lands only in the selected site, type detection, wrong-site / unknown-type / empty / missing-site refusals, duplicate flagging, CX SP scoping, path traversal, and the Graph request shapes.
