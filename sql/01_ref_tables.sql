-- ScopeIQ reference tables (schema REF). Additive only: IF NOT EXISTS everywhere; nothing is dropped or replaced.
USE DATABASE SCOPEIQ_DB;
CREATE SCHEMA IF NOT EXISTS REF COMMENT = 'Versioned reference data: BOM rules, trunk lengths, material catalog, comparison rules, workflow';

-- BOM rules (bom_rules.xlsx, sheet "BOM Rules"). Trigger and quantity are kept as written; the engine interprets them at run time.
CREATE TABLE IF NOT EXISTS REF.BOM_RULE (
  RULE_ID        VARCHAR NOT NULL,
  VERSION        NUMBER(5,0) NOT NULL DEFAULT 1,
  SEQ            NUMBER(5,0),
  TRIGGER_TEXT   VARCHAR,
  CHILD_ITEM     VARCHAR,          -- catalog key
  QUANTITY_TEXT  VARCHAR,
  NOTES          VARCHAR,
  ACTIVE         BOOLEAN DEFAULT TRUE,
  EFFECTIVE_FROM DATE,
  EFFECTIVE_TO   DATE,
  LOADED_AT      TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY      VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (RULE_ID, VERSION)
) COMMENT = 'BOM rules from bom_rules.xlsx (versioned, effective-dated)';

-- Trunk lengths (sheet "Trunk Lengths") with the factor and tower margin that the sheet note states.
CREATE TABLE IF NOT EXISTS REF.TRUNK_STEP (
  VERSION          NUMBER(5,0) NOT NULL DEFAULT 1,
  STEP_FT          NUMBER(8,2) NOT NULL,
  CATALOG_KEY      VARCHAR NOT NULL,
  TRUNK_FACTOR     NUMBER(6,3),     -- required length = factor x (vertical + horizontal run), e.g. 1.10
  TOWER_MARGIN_FT  NUMBER(6,2),     -- added to the highest new radio / AAU rad center on a tower, e.g. 5
  NOTE             VARCHAR,         -- the note text from the sheet, kept as written
  EFFECTIVE_FROM   DATE,
  EFFECTIVE_TO     DATE,
  LOADED_AT        TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY        VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (STEP_FT, VERSION)
) COMMENT = 'Trunk cable catalog steps and the sizing factor/margin (bom_rules.xlsx, sheet Trunk Lengths)';

-- Material catalog (material_catalog.xlsx, 19 columns).
CREATE TABLE IF NOT EXISTS REF.MATERIAL_CATALOG (
  CATALOG_KEY        VARCHAR NOT NULL,
  CATEGORY           VARCHAR,
  SUBCATEGORY        VARCHAR,
  MANUFACTURER       VARCHAR,
  MODEL              VARCHAR,
  MANUFACTURER_PN    VARCHAR,
  CUSTOMER_PN        VARCHAR,
  DESCRIPTION        VARCHAR,
  UOM                VARCHAR,
  SUPPLY             VARCHAR,       -- CFM / VFM
  CUSTOMER_APPROVED  VARCHAR,
  UNIT_COST_USD      NUMBER(14,2),
  RF_PORTS           NUMBER(5,0),
  POWER_W            NUMBER(8,1),
  BANDS              VARCHAR,
  TECHNOLOGY         VARCHAR,
  HEIGHT_M           NUMBER(8,3),
  WIDTH_M            NUMBER(8,3),
  DEPTH_M            NUMBER(8,3),
  VERSION            NUMBER(5,0) NOT NULL DEFAULT 1,
  LOADED_AT          TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY          VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (CATALOG_KEY, VERSION)
) COMMENT = 'Material catalog from material_catalog.xlsx';

-- Rules that compare documents and produce redlines and RFIs.
CREATE TABLE IF NOT EXISTS REF.CONSISTENCY_RULE (
  RULE_ID         VARCHAR NOT NULL,
  VERSION         NUMBER(5,0) NOT NULL DEFAULT 1,
  FAMILY          VARCHAR,
  NAME            VARCHAR,
  DESCRIPTION     VARCHAR,
  SEVERITY        VARCHAR,
  OUTCOME         VARCHAR,          -- REDLINE / RFI / ...
  TARGET_DOC      VARCHAR,
  PARAMS_JSON     VARIANT,
  STREAMS         VARCHAR,
  CARRIER         VARCHAR,
  ACTIVE          BOOLEAN DEFAULT TRUE,
  EFFECTIVE_FROM  DATE,
  EFFECTIVE_TO    DATE,
  LOADED_AT       TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY       VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (RULE_ID, VERSION)
) COMMENT = 'Cross-document comparison rules (e.g. CD vs drone)';

CREATE TABLE IF NOT EXISTS REF.REASON_CODE (
  REASON_CODE  VARCHAR NOT NULL,
  CATEGORY     VARCHAR,
  DESCRIPTION  VARCHAR,
  FAULT_PARTY  VARCHAR,
  APPLIES_TO   VARCHAR,
  LOADED_AT    TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY    VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (REASON_CODE)
) COMMENT = 'Reason codes for decisions and BOM changes';

CREATE TABLE IF NOT EXISTS REF.PERSONA (
  ROLE_CODE       VARCHAR NOT NULL,
  PERSONA_NAME    VARCHAR,
  ORGANISATION    VARCHAR,
  GOALS           VARCHAR,
  KEY_SCREENS     VARCHAR,
  SNOWFLAKE_ROLE  VARCHAR,
  CAN_APPROVE     VARCHAR,
  DATA_SCOPE      VARCHAR,
  LOADED_AT       TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY       VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (ROLE_CODE)
) COMMENT = 'Roles (personas) and what each can see and approve';

CREATE TABLE IF NOT EXISTS REF.WORKFLOW_STATE (
  ENTITY_TYPE  VARCHAR NOT NULL,
  STATE        VARCHAR NOT NULL,
  SEQ          NUMBER(5,0),
  IS_INITIAL   VARCHAR,
  IS_TERMINAL  VARCHAR,
  IS_LOCKED    VARCHAR,
  OWNER_ROLE   VARCHAR,
  DESCRIPTION  VARCHAR,
  LOADED_AT    TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY    VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (ENTITY_TYPE, STATE)
) COMMENT = 'States of each workflow entity';

CREATE TABLE IF NOT EXISTS REF.WORKFLOW_TRANSITION (
  ENTITY_TYPE       VARCHAR NOT NULL,
  FROM_STATE        VARCHAR NOT NULL,
  ACTION            VARCHAR NOT NULL,
  TO_STATE          VARCHAR,
  ALLOWED_ROLES     VARCHAR,
  REQUIRES_REASON   VARCHAR,
  REQUIRES_COMMENT  VARCHAR,
  NOTIFY_ROLES      VARCHAR,
  DESCRIPTION       VARCHAR,
  LOADED_AT         TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
  LOADED_BY         VARCHAR DEFAULT CURRENT_USER(),
  PRIMARY KEY (ENTITY_TYPE, FROM_STATE, ACTION)
) COMMENT = 'Allowed status changes: who may do what, and what it notifies';
