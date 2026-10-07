# Data model
Generated from `scopeiq/db/schema.py`, the single schema registry used for both SQLite (local) and Snowflake (`snowflake/03_tables.sql`).

## RAW

### RAW.ST_SITE

SiteTracker Site export

| Column | Type | Key |
|---|---|---|
| ID | text | PK |
| NAME | text |  |
| SITE_NAME__C | text |  |
| MARKET__C | text |  |
| CUSTOMER__C | text |  |
| STREET__C | text |  |
| CITY__C | text |  |
| STATE__C | text |  |
| ZIP__C | text |  |
| LATITUDE__C | decimal |  |
| LONGITUDE__C | decimal |  |
| STRUCTURE_TYPE__C | text |  |
| STRUCTURE_HEIGHT_FT__C | decimal |  |
| STRUCTURE_OWNER__C | text |  |
| SITE_STATUS__C | text |  |
| LOADED_AT | timestamp |  |

### RAW.ST_PROJECT

SiteTracker Project export

| Column | Type | Key |
|---|---|---|
| ID | text | PK |
| NAME | text |  |
| SITE__C | text |  |
| PROJECT_TYPE__C | text |  |
| SCOPING_SERVICE_LINE__C | text |  |
| SCOPING_ASSIGNED_DATE__C | text |  |
| BOM_STATUS__C | text |  |
| CURRENT_BOM_REV__C | text |  |
| CX_SERVICE_PROVIDER__C | text |  |
| SCOPING_COMPLETE_FORECAST__C | text |  |
| SCOPING_COMPLETE_ACTUAL__C | text |  |
| FBA_DATE__C | text |  |
| LOADED_AT | timestamp |  |

### RAW.ST_MILESTONE

SiteTracker Milestone export

| Column | Type | Key |
|---|---|---|
| ID | text | PK |
| PROJECT__C | text |  |
| NAME | text |  |
| FORECAST_DATE__C | text |  |
| ACTUAL_DATE__C | text |  |
| STATUS__C | text |  |
| SEQUENCE__C | decimal |  |
| LOADED_AT | timestamp |  |

### RAW.ST_DOCUMENT

SiteTracker Document export

| Column | Type | Key |
|---|---|---|
| ID | text | PK |
| PROJECT__C | text |  |
| DOCUMENT_TYPE__C | text |  |
| TITLE | text |  |
| FILE_PATH__C | text |  |
| FILE_FORMAT__C | text |  |
| REVISION__C | text |  |
| UPLOADED_DATE__C | text |  |
| LOADED_AT | timestamp |  |

## REF

### REF.MATERIAL_CATALOG

Reference data from material_catalog.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| CATALOG_KEY | text | PK |
| CATEGORY | text |  |
| SUBCATEGORY | text |  |
| MANUFACTURER | text |  |
| MODEL | text |  |
| MANUFACTURER_PN | text |  |
| CUSTOMER_PN | text |  |
| DESCRIPTION | text |  |
| UOM | text |  |
| SUPPLY | text |  |
| CUSTOMER_APPROVED | text |  |
| UNIT_COST_USD | decimal |  |
| RF_PORTS | decimal |  |
| POWER_W | decimal |  |
| BANDS | text |  |
| TECHNOLOGY | text |  |
| HEIGHT_M | decimal |  |
| WIDTH_M | decimal |  |
| DEPTH_M | decimal |  |
| ALIASES | text |  |
| VERSION | decimal |  |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.KIT_RULE

Reference data from kit_rules.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| RULE_ID | text | PK |
| TRIGGER_CODE | text |  |
| TRIGGER_TEXT | text |  |
| CHILD_KEY | text |  |
| QTY_EXPR | text |  |
| SPARE_EXPR | text |  |
| SCOPE | text |  |
| SOURCE_TEMPLATE | text |  |
| NOTES | text |  |
| CARRIER | text |  |
| VERSION | decimal | PK |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.TRUNK_STEP

Reference data from trunk_steps.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| STEP_FT | decimal | PK |
| CATALOG_KEY | text |  |
| RULE_TEXT | text |  |
| VERSION | decimal | PK |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.CONSISTENCY_RULE

Reference data from consistency_rules.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| RULE_ID | text | PK |
| FAMILY | text |  |
| NAME | text |  |
| DESCRIPTION | text |  |
| SEVERITY | text |  |
| OUTCOME | text |  |
| TARGET_DOC | text |  |
| PARAMS_JSON | text |  |
| STREAMS | text |  |
| CARRIER | text |  |
| ACTIVE | text |  |
| VERSION | decimal | PK |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.SERVICE_DRIVER_MATRIX

Reference data from service_driver_matrix.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| DRIVER_CODE | text | PK |
| DESCRIPTION | text |  |
| DELTA_ACTION | text |  |
| EQUIPMENT_CLASS | text |  |
| UOM | text |  |
| QTY_BASIS | text |  |
| NOTES | text |  |
| VERSION | decimal | PK |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.RATE_CARD

Reference data from rate_card.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| MARKET | text | PK |
| SERVICE_PROVIDER | text | PK |
| DRIVER_CODE | text | PK |
| UNIT_RATE_USD | decimal |  |
| VERSION | decimal | PK |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| NOTES | text |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.SITE_REQUIREMENT_RULE

Reference data from site_requirement_rules.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| RULE_ID | text | PK |
| PRIORITY | decimal |  |
| STRUCTURE_TYPE | text |  |
| MIN_HEIGHT_FT | decimal |  |
| MAX_HEIGHT_FT | decimal |  |
| MIN_NEW_LOAD_LB | decimal |  |
| REQUIRES_AAU | text |  |
| ACCESS_METHOD | text |  |
| CRANE_DAYS | decimal |  |
| MANLIFT_DAYS | decimal |  |
| RIGGING_CLASS | text |  |
| EHS_ALERT | text |  |
| DESCRIPTION | text |  |
| VERSION | decimal | PK |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.CYCLE_TIME_PARAM

Reference data from cycle_time_params.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| PARAM | text | PK |
| VALUE | decimal |  |
| UOM | text |  |
| DESCRIPTION | text |  |
| VERSION | decimal | PK |
| EFFECTIVE_FROM | date |  |
| EFFECTIVE_TO | date |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.REASON_CODE

Reference data from reason_codes.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| REASON_CODE | text | PK |
| CATEGORY | text |  |
| DESCRIPTION | text |  |
| FAULT_PARTY | text |  |
| APPLIES_TO | text |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.PERSONA

Reference data from personas.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| ROLE_CODE | text | PK |
| PERSONA_NAME | text |  |
| ORGANISATION | text |  |
| GOALS | text |  |
| KEY_SCREENS | text |  |
| SNOWFLAKE_ROLE | text |  |
| CAN_APPROVE | text |  |
| DATA_SCOPE | text |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.APP_USER

Reference data from users.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| USER_ID | text | PK |
| DISPLAY_NAME | text |  |
| EMAIL | text |  |
| ROLE_CODE | text |  |
| ORGANISATION | text |  |
| MARKET | text |  |
| SERVICE_PROVIDER | text |  |
| ACTIVE | text |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.WORKFLOW_STATE

Reference data from workflow_states.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| ENTITY_TYPE | text | PK |
| STATE | text | PK |
| SEQ | decimal |  |
| IS_INITIAL | text |  |
| IS_TERMINAL | text |  |
| IS_LOCKED | text |  |
| OWNER_ROLE | text |  |
| DESCRIPTION | text |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

### REF.WORKFLOW_TRANSITION

Reference data from workflow_transitions.csv (versioned, effective-dated)

| Column | Type | Key |
|---|---|---|
| ENTITY_TYPE | text | PK |
| FROM_STATE | text | PK |
| ACTION | text | PK |
| TO_STATE | text |  |
| ALLOWED_ROLES | text |  |
| REQUIRES_REASON | text |  |
| REQUIRES_COMMENT | text |  |
| NOTIFY_ROLES | text |  |
| DESCRIPTION | text |  |
| LOADED_AT | timestamp |  |
| LOADED_BY | text |  |

## CORE

### CORE.SITE

One row per site (SiteTracker + RFDS site info + workflow state)

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| SF_ID | text |  |
| SITE_NAME | text |  |
| MARKET | text |  |
| CUSTOMER | text |  |
| ADDRESS | text |  |
| CITY | text |  |
| STATE | text |  |
| ZIP | text |  |
| LATITUDE | decimal |  |
| LONGITUDE | decimal |  |
| STRUCTURE_TYPE | text |  |
| HEIGHT_FT | decimal |  |
| STRUCTURE_OWNER | text |  |
| SITE_STATUS | text |  |
| STREAM | text |  |
| PROJECT_SF_ID | text |  |
| PROJECT_NAME | text |  |
| PROJECT_TYPE | text |  |
| SERVICE_LINE | text |  |
| CX_SP | text |  |
| ASSIGNED_DATE | text |  |
| SCOPING_FORECAST | text |  |
| SCOPING_ACTUAL | text |  |
| FBA_DATE | text |  |
| CURRENT_BOM_REV | text |  |
| WORKFLOW_STATE | text |  |
| ASSIGNED_TO | text |  |
| LAST_RUN_ID | text |  |
| UPDATED_AT | timestamp |  |
| UPDATED_BY | text |  |

### CORE.MILESTONE

SiteTracker milestones

| Column | Type | Key |
|---|---|---|
| MILESTONE_SF_ID | text | PK |
| SITE_ID | text | not null |
| NAME | text |  |
| SEQ | integer |  |
| FORECAST | text |  |
| ACTUAL | text |  |
| STATUS | text |  |

### CORE.DOCUMENT

Document registry (latest revision = CURRENT)

| Column | Type | Key |
|---|---|---|
| DOC_ID | text | PK |
| SITE_ID | text | not null |
| DOC_TYPE | text |  |
| FILE_NAME | text |  |
| REL_PATH | text |  |
| FILE_FORMAT | text |  |
| REVISION | text |  |
| REVISION_RANK | integer |  |
| FILE_HASH | text |  |
| SIZE_BYTES | integer |  |
| DOC_DATE | text |  |
| SOURCE | text |  |
| STATUS | text |  |
| REGISTERED_AT | timestamp |  |
| REGISTERED_BY | text |  |

### CORE.UPLOAD

Artifacts uploaded through the app before registration

| Column | Type | Key |
|---|---|---|
| UPLOAD_ID | text | PK |
| SITE_ID | text | not null |
| DOC_TYPE | text |  |
| FILE_NAME | text |  |
| STAGE_PATH | text |  |
| SIZE_BYTES | integer |  |
| FILE_HASH | text |  |
| UPLOADED_BY | text |  |
| UPLOADED_AT | timestamp |  |
| STATUS | text |  |
| DOC_ID | text |  |
| MESSAGE | text |  |

### CORE.PIPELINE_RUN

One row per pipeline execution for a site

| Column | Type | Key |
|---|---|---|
| RUN_ID | text | PK |
| SITE_ID | text | not null |
| STARTED_AT | timestamp |  |
| FINISHED_AT | timestamp |  |
| STATUS | text |  |
| TRIGGERED_BY | text |  |
| CORRELATION_ID | text |  |
| STEPS | JSON / VARIANT |  |
| SUMMARY | JSON / VARIANT |  |
| WARNINGS | JSON / VARIANT |  |
| REFERENCE_VERSIONS | JSON / VARIANT |  |

### CORE.EXTRACTED_FIELD

Every value read from a document, with confidence

| Column | Type | Key |
|---|---|---|
| FIELD_ID | text | PK |
| RUN_ID | text |  |
| SITE_ID | text | not null |
| DOC_ID | text |  |
| PAGE | text |  |
| FIELD_NAME | text |  |
| VALUE | JSON / VARIANT |  |
| CONFIDENCE | decimal |  |
| METHOD | text |  |
| NEEDS_REVIEW | boolean |  |
| REVIEWED_BY | text |  |
| REVIEWED_AT | timestamp |  |

### CORE.CONFIG_LINE

Equipment per source (RFDS/CD/FIELD/MA)

| Column | Type | Key |
|---|---|---|
| LINE_ID | text | PK |
| RUN_ID | text |  |
| SITE_ID | text | not null |
| SOURCE | text |  |
| SECTOR | text |  |
| POSITION | integer |  |
| KIND | text |  |
| CATALOG_KEY | text |  |
| MODEL_TEXT | text |  |
| STATUS | text |  |
| RAD_CENTER_FT | decimal |  |
| AZIMUTH_DEG | decimal |  |
| MECH_TILT | decimal |  |
| BANDS | text |  |
| SOURCE_REF | text |  |
| CONFIDENCE | decimal |  |
| ATTRS | JSON / VARIANT |  |

### CORE.SECTOR_INFO

Sector azimuths and mounts per source

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| SECTOR | text | PK |
| AZ_RFDS | decimal |  |
| AZ_CD | decimal |  |
| AZ_FIELD | decimal |  |
| NEW_FRAME | boolean |  |
| SLED_CD | boolean |  |
| SLED_FIELD | boolean |  |

### CORE.TRUNK_MEASURE

Cable schedule (CD) and measured route (FIELD)

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| SOURCE | text | PK |
| TRUNK_COUNT | integer |  |
| VERTICAL_FT | decimal |  |
| HORIZONTAL_FT | decimal |  |
| REQUIRED_FT | decimal |  |
| SPECIFIED_FT | decimal |  |
| SOURCE_REF | text |  |

### CORE.ANALYSIS_RESULT

Mount (MA) and structural (SA) analysis results

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| KIND | text | PK |
| REPORT_ID | text |  |
| REPORT_DATE | text |  |
| RESULT | text |  |
| CAPACITY_PCT | decimal |  |
| CAPACITY_AFTER_PCT | decimal |  |
| RFDS_REVISION | text |  |
| MODIFICATIONS | JSON / VARIANT |  |
| SOURCE_REF | text |  |

### CORE.REV0_LINE

REV 0 preliminary BOM rows as read

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| ROW_NUM | integer | PK |
| SECTOR | text |  |
| CATALOG_KEY | text |  |
| MODEL | text |  |
| MFR_PN | text |  |
| CUSTOMER_PN | text |  |
| DESIGN_QTY | decimal |  |
| SPARE_QTY | decimal |  |
| ACTION | text |  |
| RULE_ID | text |  |
| SOURCE | text |  |

### CORE.FIELD_OBJECT

Drone survey objects (vendor CSV or point cloud)

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| OBJECT_ID | text | PK |
| OBJECT_TYPE | text |  |
| SECTOR | text |  |
| POSITION | integer |  |
| BEARING_DEG | decimal |  |
| FACING_AZ_DEG | decimal |  |
| CENTER_HEIGHT_FT | decimal |  |
| DIMS_IN | JSON / VARIANT |  |
| MODEL_GUESS | text |  |
| CONFIDENCE | decimal |  |
| ROUTE_LENGTH_FT | decimal |  |
| METHOD | text |  |

### CORE.EVIDENCE_FRAME

Frames sampled from the drone orbit video

| Column | Type | Key |
|---|---|---|
| FRAME_ID | text | PK |
| RUN_ID | text |  |
| SITE_ID | text | not null |
| FRAME_INDEX | integer |  |
| TIME_S | decimal |  |
| BEARING_DEG | decimal |  |
| SECTOR | text |  |
| SHARPNESS | decimal |  |
| PATH | text |  |
| SELECTED | boolean |  |

### CORE.DISCREPANCY

Findings; id is stable across runs so human decisions survive re-runs

| Column | Type | Key |
|---|---|---|
| DISC_ID | text | PK |
| SITE_ID | text | not null |
| RUN_ID | text |  |
| RULE_ID | text |  |
| FAMILY | text |  |
| SEVERITY | text |  |
| OUTCOME | text |  |
| TITLE | text |  |
| DESCRIPTION | text |  |
| SECTOR | text |  |
| POSITION | integer |  |
| EXPECTED | JSON / VARIANT |  |
| FOUND | JSON / VARIANT |  |
| GOVERNING | text |  |
| SOURCES | JSON / VARIANT |  |
| TARGET_DOC | text |  |
| TARGET_SHEET | text |  |
| BOM_IMPACT | text |  |
| EVIDENCE | JSON / VARIANT |  |
| CONFIDENCE | decimal |  |
| STATUS | text |  |
| REASON_CODE | text |  |
| ASSIGNED_TO | text |  |
| FIRST_SEEN_RUN | text |  |
| LAST_SEEN_RUN | text |  |
| CREATED_AT | timestamp |  |
| UPDATED_AT | timestamp |  |
| UPDATED_BY | text |  |

### CORE.EQUIPMENT_DELTA

NEW / EXISTING / REMOVED / RELOCATED / REUSED per device

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| SEQ | integer | PK |
| SECTOR | text |  |
| POSITION | integer |  |
| KIND | text |  |
| CATALOG_KEY | text |  |
| ACTION | text |  |
| FROM_POSITION | integer |  |
| RAD_CENTER_FT | decimal |  |
| BASIS | text |  |
| SOURCE_REF | text |  |

### CORE.BOM_REVISION

BOM revisions: REV 0 (tool), REV 1..n (generated/edited); FBA revisions are locked

| Column | Type | Key |
|---|---|---|
| BOM_REV_ID | text | PK |
| SITE_ID | text | not null |
| REV_NO | integer |  |
| REV_LABEL | text |  |
| KIND | text |  |
| STATUS | text |  |
| LOCKED | boolean |  |
| RUN_ID | text |  |
| PARENT_REV_ID | text |  |
| REASON_CODE | text |  |
| TRUNK_PLAN | JSON / VARIANT |  |
| TOTALS | JSON / VARIANT |  |
| CREATED_AT | timestamp |  |
| CREATED_BY | text |  |
| APPROVED_AT | timestamp |  |
| APPROVED_BY | text |  |
| NOTES | text |  |

### CORE.BOM_LINE

BOM lines with rule ID and source reference

| Column | Type | Key |
|---|---|---|
| LINE_ID | text | PK |
| BOM_REV_ID | text | not null |
| SITE_ID | text | not null |
| SECTOR | text |  |
| CATALOG_KEY | text |  |
| DESIGN_QTY | decimal |  |
| SPARE_QTY | decimal |  |
| TOTAL_QTY | decimal |  |
| ACTION | text |  |
| RULE_ID | text |  |
| SOURCE | text |  |
| PARENT_KEY | text |  |
| REASON_CODE | text |  |
| TRACE | JSON / VARIANT |  |
| EDITED_BY | text |  |
| EDITED_AT | timestamp |  |

### CORE.BOM_CHANGE

Line-level differences between two revisions with reasons

| Column | Type | Key |
|---|---|---|
| CHANGE_ID | text | PK |
| SITE_ID | text | not null |
| FROM_REV_ID | text |  |
| TO_REV_ID | text |  |
| SECTOR | text |  |
| CATALOG_KEY | text |  |
| ACTION | text |  |
| FROM_QTY | decimal |  |
| TO_QTY | decimal |  |
| DELTA | decimal |  |
| REASONS | JSON / VARIANT |  |

### CORE.DRIVER_LINE

Service drivers (FPP codes) with illustrative rates

| Column | Type | Key |
|---|---|---|
| LINE_ID | text | PK |
| RUN_ID | text |  |
| SITE_ID | text | not null |
| DRIVER_CODE | text |  |
| DESCRIPTION | text |  |
| SECTOR | text |  |
| QTY | decimal |  |
| UOM | text |  |
| UNIT_RATE | decimal |  |
| AMOUNT | decimal |  |
| BASIS | text |  |

### CORE.SITE_REQUIREMENT

Access, rigging and hold requirements

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| RULE_ID | text |  |
| ACCESS_METHOD | text |  |
| CRANE_DAYS | decimal |  |
| MANLIFT_DAYS | decimal |  |
| RIGGING_CLASS | text |  |
| HOLD | boolean |  |
| INPUTS | JSON / VARIANT |  |

### CORE.ESTIMATE

Cost and cycle-time estimate

| Column | Type | Key |
|---|---|---|
| SITE_ID | text | PK |
| RUN_ID | text | PK |
| CYCLE_DAYS | decimal |  |
| SERVICES_USD | decimal |  |
| MATERIAL_USD | decimal |  |
| TOTAL_USD | decimal |  |
| DETAIL | JSON / VARIANT |  |

### CORE.EHS_ALERT

EH&S alerts (rooftop crane, guyed tower, SA fail)

| Column | Type | Key |
|---|---|---|
| ALERT_ID | text | PK |
| SITE_ID | text | not null |
| RULE_ID | text |  |
| SEVERITY | text |  |
| ALERT_TEXT | text |  |
| STATUS | text |  |
| CREATED_AT | timestamp |  |
| UPDATED_AT | timestamp |  |
| UPDATED_BY | text |  |

### CORE.REDLINE

Redlines to apply to CD / MA documents

| Column | Type | Key |
|---|---|---|
| REDLINE_ID | text | PK |
| SITE_ID | text | not null |
| DISC_ID | text |  |
| DOC_TYPE | text |  |
| DOC_REVISION | text |  |
| SHEET | text |  |
| MARKUP | text |  |
| CHANGE_FROM | text |  |
| CHANGE_TO | text |  |
| STATUS | text |  |
| PDF_PATH | text |  |
| CREATED_AT | timestamp |  |
| UPDATED_AT | timestamp |  |
| UPDATED_BY | text |  |

### CORE.RFI

Requests for information

| Column | Type | Key |
|---|---|---|
| RFI_ID | text | PK |
| SITE_ID | text | not null |
| TO_PARTY | text |  |
| SUBJECT | text |  |
| QUESTION | text |  |
| PROPOSED_ANSWER | text |  |
| ANSWER | text |  |
| DISC_IDS | JSON / VARIANT |  |
| STATUS | text |  |
| CREATED_AT | timestamp |  |
| UPDATED_AT | timestamp |  |
| UPDATED_BY | text |  |

## WF

### WF.WORKFLOW_EVENT

Every workflow transition (status history)

| Column | Type | Key |
|---|---|---|
| EVENT_ID | text | PK |
| ENTITY_TYPE | text | not null |
| ENTITY_ID | text | not null |
| SITE_ID | text |  |
| FROM_STATE | text |  |
| ACTION | text |  |
| TO_STATE | text |  |
| ACTOR_USER_ID | text |  |
| ACTOR_ROLE | text |  |
| REASON_CODE | text |  |
| COMMENT | text |  |
| EVENT_TS | timestamp |  |
| CORRELATION_ID | text |  |

### WF.NOTIFICATION

Role inbox items created by transitions

| Column | Type | Key |
|---|---|---|
| NOTIFICATION_ID | text | PK |
| ROLE_CODE | text |  |
| USER_ID | text |  |
| SITE_ID | text |  |
| ENTITY_TYPE | text |  |
| ENTITY_ID | text |  |
| MESSAGE | text |  |
| CREATED_AT | timestamp |  |
| READ_AT | timestamp |  |

### WF.COMMENT

Free-text comments

| Column | Type | Key |
|---|---|---|
| COMMENT_ID | text | PK |
| ENTITY_TYPE | text |  |
| ENTITY_ID | text |  |
| SITE_ID | text |  |
| USER_ID | text |  |
| COMMENT_TEXT | text |  |
| CREATED_AT | timestamp |  |

## AUDIT

### AUDIT.AUDIT_LOG

Who changed what, when and why (immutable)

| Column | Type | Key |
|---|---|---|
| AUDIT_ID | text | PK |
| EVENT_TS | timestamp |  |
| ENTITY_TYPE | text |  |
| ENTITY_ID | text |  |
| SITE_ID | text |  |
| ACTION | text |  |
| ACTOR_USER_ID | text |  |
| ACTOR_ROLE | text |  |
| REASON_CODE | text |  |
| COMMENT | text |  |
| BEFORE_VALUE | JSON / VARIANT |  |
| AFTER_VALUE | JSON / VARIANT |  |
| CORRELATION_ID | text |  |
| SOURCE | text |  |

### AUDIT.APP_LOG

Application log sink (level set per environment)

| Column | Type | Key |
|---|---|---|
| LOG_ID | text | PK |
| LOG_TS | timestamp |  |
| LEVEL | text |  |
| LOGGER | text |  |
| MESSAGE | text |  |
| CORRELATION_ID | text |  |
| USER_ID | text |  |
| SITE_ID | text |  |
| COMPONENT | text |  |
| DETAIL | JSON / VARIANT |  |

### AUDIT.ERROR_LOG

Errors with stack and context

| Column | Type | Key |
|---|---|---|
| ERROR_ID | text | PK |
| ERROR_TS | timestamp |  |
| ERROR_CODE | text |  |
| MESSAGE | text |  |
| EXCEPTION_TYPE | text |  |
| STACK | text |  |
| WHERE_RAISED | text |  |
| CORRELATION_ID | text |  |
| USER_ID | text |  |
| SITE_ID | text |  |
| COMPONENT | text |  |
| DETAILS | JSON / VARIANT |  |
