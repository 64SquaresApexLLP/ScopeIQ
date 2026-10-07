# API reference
Generated from the FastAPI application by `backend/scripts/generate_docs.py` (interactive version at `http://localhost:8000/docs` while the API runs).

Authentication: `POST /auth/login` with `{"user_id": "scoper1", "password": "demo"}` returns a token; send `Authorization: Bearer <token>` on every other call (file downloads also accept `?access_token=`). Roles are enforced per endpoint and, for workflow actions, by the workflow tables (see PERSONAS_AND_WORKFLOWS.md).

Errors always use one envelope: `{"error": {"code": "SIQ-NF-404", "message": "...", "correlation_id": "...", "details": {...}}}`. Codes: SIQ-VAL-400 invalid input, SIQ-AUTH-401 not signed in, SIQ-AUTH-403 role not allowed, SIQ-NF-404 not found, SIQ-CONF-409 / SIQ-WF-409 / SIQ-LOCK-409 conflict, workflow or locked record, SIQ-EXT-422 document unreadable, SIQ-DB-503 database unavailable, SIQ-SYS-500 unexpected. Every response carries `X-Correlation-ID`.

## auth

### `GET /auth/users`

Demo accounts and personas for the login screen.


### `POST /auth/login`

Login


Body (`application/json`, LoginIn):

| Field | Required | Type |
|---|---|---|
| user_id | yes | string |
| password | no | string |

### `GET /auth/me`

Me


## sites

### `GET /sites`

List Sites


### `GET /sites/dashboard`

Dashboard


### `GET /sites/{site_id}`

Site Detail

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |

### `GET /sites/{site_id}/config`

Config Lines

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |
| source | query | no | string/null |

### `GET /sites/{site_id}/evidence`

Evidence

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |
| selected_only | query | no | boolean |

### `GET /sites/{site_id}/fields`

Extracted Fields

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |
| needs_review | query | no | boolean/null |

## documents

### `GET /sites/{site_id}/documents`

List Documents

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |

### `POST /sites/{site_id}/documents/upload`

Upload

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |

Body (`multipart/form-data`, Body_upload_sites__site_id__documents_upload_post):

| Field | Required | Type |
|---|---|---|
| doc_type | yes | string |
| file | yes | string |

### `GET /documents/{doc_id}/download`

Download

| Parameter | In | Required | Type |
|---|---|---|---|
| doc_id | path | yes | string |

## pipeline

### `POST /pipeline/sites/{site_id}/run`

Run Site

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |

### `POST /pipeline/run`

Run Many


Body (`application/json`, RunIn):

| Field | Required | Type |
|---|---|---|
| site_ids | no | array/null |

### `GET /pipeline/runs`

Runs

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | query | no | string/null |
| limit | query | no | integer |

### `GET /pipeline/sites`

Available Sites


## discrepancies

### `GET /discrepancies`

List Discrepancies

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | query | no | string/null |
| status | query | no | string/null |
| outcome | query | no | string/null |
| severity | query | no | string/null |
| rule_id | query | no | string/null |
| assigned_to | query | no | string/null |

### `GET /discrepancies/{disc_id}`

Get Discrepancy

| Parameter | In | Required | Type |
|---|---|---|---|
| disc_id | path | yes | string |

### `POST /discrepancies/{disc_id}/transition`

Transition

| Parameter | In | Required | Type |
|---|---|---|---|
| disc_id | path | yes | string |

Body (`application/json`, TransitionIn):

| Field | Required | Type |
|---|---|---|
| action | yes | string |
| reason_code | no | string/null |
| comment | no | string/null |

### `POST /discrepancies/{disc_id}/assign`

Assign

| Parameter | In | Required | Type |
|---|---|---|---|
| disc_id | path | yes | string |

Body (`application/json`, AssignIn):

| Field | Required | Type |
|---|---|---|
| user_id | yes | string |

### `POST /discrepancies/{disc_id}/comments`

Comment

| Parameter | In | Required | Type |
|---|---|---|---|
| disc_id | path | yes | string |

Body (`application/json`, CommentIn):

| Field | Required | Type |
|---|---|---|
| text | yes | string |

## redlines & RFIs

### `GET /redlines`

List Redlines

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | query | no | string/null |
| status | query | no | string/null |

### `POST /redlines/{redline_id}/transition`

Redline Transition

| Parameter | In | Required | Type |
|---|---|---|---|
| redline_id | path | yes | string |

Body (`application/json`, TransitionIn):

| Field | Required | Type |
|---|---|---|
| action | yes | string |
| reason_code | no | string/null |
| comment | no | string/null |

### `GET /rfis`

List Rfis

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | query | no | string/null |
| status | query | no | string/null |

### `POST /rfis/{rfi_id}/transition`

Rfi Transition

| Parameter | In | Required | Type |
|---|---|---|---|
| rfi_id | path | yes | string |

Body (`application/json`, TransitionIn):

| Field | Required | Type |
|---|---|---|
| action | yes | string |
| reason_code | no | string/null |
| comment | no | string/null |

### `POST /rfis/{rfi_id}/answer`

Answer Rfi

| Parameter | In | Required | Type |
|---|---|---|---|
| rfi_id | path | yes | string |

Body (`application/json`, RfiAnswerIn):

| Field | Required | Type |
|---|---|---|
| answer | yes | string |

## bom

### `GET /bom/revisions`

Approval queues: e.g. IN_REVIEW for the reviewer, SP_REVIEW for the CX SP, SP_AGREED for Ericsson.

| Parameter | In | Required | Type |
|---|---|---|---|
| status | query | no | string/null |

### `GET /bom/sites/{site_id}/revisions`

Revisions

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |

### `GET /bom/revisions/{rev_id}`

Revision

| Parameter | In | Required | Type |
|---|---|---|---|
| rev_id | path | yes | string |

### `GET /bom/revisions/{rev_id}/lines`

Lines

| Parameter | In | Required | Type |
|---|---|---|---|
| rev_id | path | yes | string |

### `POST /bom/revisions/{rev_id}/lines`

Add Line

| Parameter | In | Required | Type |
|---|---|---|---|
| rev_id | path | yes | string |

Body (`application/json`, BomLineAddIn):

| Field | Required | Type |
|---|---|---|
| sector | yes | string |
| catalog_key | yes | string |
| design_qty | yes | number |
| spare_qty | no | number |
| action | no | string |
| reason_code | yes | string |
| comment | no | string/null |

### `GET /bom/revisions/{rev_id}/changes`

Changes

| Parameter | In | Required | Type |
|---|---|---|---|
| rev_id | path | yes | string |

### `PATCH /bom/lines/{line_id}`

Edit Line

| Parameter | In | Required | Type |
|---|---|---|---|
| line_id | path | yes | string |

Body (`application/json`, BomLineEditIn):

| Field | Required | Type |
|---|---|---|
| design_qty | no | number/null |
| spare_qty | no | number/null |
| reason_code | yes | string |
| comment | no | string/null |

### `DELETE /bom/lines/{line_id}`

Delete Line

| Parameter | In | Required | Type |
|---|---|---|---|
| line_id | path | yes | string |
| reason_code | query | yes | string |
| comment | query | no | string/null |

### `POST /bom/revisions/{rev_id}/transition`

Transition

| Parameter | In | Required | Type |
|---|---|---|---|
| rev_id | path | yes | string |

Body (`application/json`, TransitionIn):

| Field | Required | Type |
|---|---|---|
| action | yes | string |
| reason_code | no | string/null |
| comment | no | string/null |

### `GET /bom/revisions/{rev_id}/export`

Export

| Parameter | In | Required | Type |
|---|---|---|---|
| rev_id | path | yes | string |

## estimate

### `GET /sites/{site_id}/delta`

Delta

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |

### `GET /sites/{site_id}/estimate`

Site Estimate

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | path | yes | string |

### `GET /ehs-alerts`

Ehs Alerts

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | query | no | string/null |
| status | query | no | string/null |

### `POST /ehs-alerts/{alert_id}/transition`

Ehs Transition

| Parameter | In | Required | Type |
|---|---|---|---|
| alert_id | path | yes | string |

Body (`application/json`, TransitionIn):

| Field | Required | Type |
|---|---|---|
| action | yes | string |
| reason_code | no | string/null |
| comment | no | string/null |

## workflow

### `GET /workflow/definition`

Definition


### `GET /workflow/{entity}/{entity_id}/actions`

Actions

| Parameter | In | Required | Type |
|---|---|---|---|
| entity | path | yes | string |
| entity_id | path | yes | string |

### `POST /workflow/{entity}/{entity_id}/transition`

Transition

| Parameter | In | Required | Type |
|---|---|---|---|
| entity | path | yes | string |
| entity_id | path | yes | string |

Body (`application/json`, TransitionIn):

| Field | Required | Type |
|---|---|---|
| action | yes | string |
| reason_code | no | string/null |
| comment | no | string/null |

### `GET /workflow/{entity}/{entity_id}/history`

History

| Parameter | In | Required | Type |
|---|---|---|---|
| entity | path | yes | string |
| entity_id | path | yes | string |

### `GET /workflow/inbox`

Inbox

| Parameter | In | Required | Type |
|---|---|---|---|
| unread_only | query | no | boolean |
| limit | query | no | integer |

### `POST /workflow/inbox/{notification_id}/read`

Mark Read

| Parameter | In | Required | Type |
|---|---|---|---|
| notification_id | path | yes | string |

## admin

### `GET /reference`

Reference Tables


### `GET /reference/{table}`

Reference Rows

| Parameter | In | Required | Type |
|---|---|---|---|
| table | path | yes | string |

### `GET /reference-codes/reasons`

Reason Codes


### `POST /reference/reload`

Reload


### `GET /audit`

Audit

| Parameter | In | Required | Type |
|---|---|---|---|
| site_id | query | no | string/null |
| entity_type | query | no | string/null |
| entity_id | query | no | string/null |
| limit | query | no | integer |

### `GET /logs/app`

App Logs

| Parameter | In | Required | Type |
|---|---|---|---|
| level | query | no | string/null |
| limit | query | no | integer |

### `GET /logs/errors`

Error Logs

| Parameter | In | Required | Type |
|---|---|---|---|
| limit | query | no | integer |

### `GET /config`

Runtime Config


### `POST /logs/client`

The mobile app forwards its warnings and errors here (level threshold set by the app's environment).


Body (`application/json`, ClientLogIn):

| Field | Required | Type |
|---|---|---|
| level | no | string |
| message | yes | string |
| context | no | object/null |

## health

### `GET /health`

Health

