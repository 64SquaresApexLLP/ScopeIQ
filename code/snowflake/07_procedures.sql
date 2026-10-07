-- =====================================================================================================
-- 07  Settings table and Snowpark procedures.
--     APP.SP_RUN_PIPELINE(site_ids, triggered_by)  runs the ScopeIQ pipeline (same Python package as the API)
--     APP.SP_RUN_CHANGED_SITES()                    runs it for sites whose staged files changed (used by the task)
--     Prerequisites: 02 (stages), dist/scopeiq_code.zip uploaded to @RAW.SCOPEIQ_CODE, 03 and 05 loaded.
-- =====================================================================================================
USE ROLE IDENTIFIER($SCOPEIQ_ADMIN_ROLE);
USE DATABASE IDENTIFIER($SCOPEIQ_DB);
USE WAREHOUSE IDENTIFIER($SCOPEIQ_WH);
USE SCHEMA APP;

-- Environment settings the procedures read at run time (the values come from config/env_<env>.sql).
CREATE TABLE IF NOT EXISTS APP.SETTINGS (KEY VARCHAR PRIMARY KEY, VALUE VARCHAR, UPDATED_AT TIMESTAMP_TZ);
MERGE INTO APP.SETTINGS t USING (
  SELECT 'SCOPEIQ_ENV' AS KEY, $SCOPEIQ_ENV AS VALUE UNION ALL
  SELECT 'APP_LOG_LEVEL', $SCOPEIQ_APP_LOG_LEVEL UNION ALL
  SELECT 'WAREHOUSE', $SCOPEIQ_WH
) s ON t.KEY = s.KEY
WHEN MATCHED THEN UPDATE SET VALUE = s.VALUE, UPDATED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (KEY, VALUE, UPDATED_AT) VALUES (s.KEY, s.VALUE, CURRENT_TIMESTAMP());

-- Python packages come from PyPI through Snowflake's shared artifact repository (needs the database role below).
-- If your account cannot use it, see EXECUTION_GUIDE.md section 7 (Snowpark Container Services job).
USE ROLE ACCOUNTADMIN;
GRANT DATABASE ROLE SNOWFLAKE.PYPI_REPOSITORY_USER TO ROLE IDENTIFIER($SCOPEIQ_ADMIN_ROLE);
USE ROLE IDENTIFIER($SCOPEIQ_ADMIN_ROLE);

CREATE OR REPLACE PROCEDURE APP.SP_RUN_PIPELINE(SITE_IDS VARCHAR DEFAULT '', TRIGGERED_BY VARCHAR DEFAULT 'manual')
  RETURNS VARIANT
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  ARTIFACT_REPOSITORY = snowflake.snowpark.pypi_shared_repository
  PACKAGES = ('snowflake-snowpark-python', 'pyyaml', 'openpyxl', 'ezdxf', 'laspy', 'numpy', 'opencv-python-headless', 'pypdf',
              'reportlab', 'pymupdf')
  IMPORTS = ('@RAW.SCOPEIQ_CODE/scopeiq_code.zip')
  HANDLER = 'main'
  COMMENT = 'Run the ScopeIQ pipeline for a comma-separated list of sites (empty = every staged site)'
  EXECUTE AS OWNER
AS
$$
import json
import os
import sys
import zipfile

TARGET = "/tmp/scopeiq_code"


def main(session, site_ids, triggered_by):
    # The zip holds backend/scopeiq and reference_data with the same layout as the code/ folder.
    if not os.path.isdir(os.path.join(TARGET, "backend", "scopeiq")):
        with zipfile.ZipFile(os.path.join(sys._xoptions["snowflake_import_directory"], "scopeiq_code.zip")) as z:
            z.extractall(TARGET)
    sys.path.insert(0, os.path.join(TARGET, "backend"))
    from scopeiq.services.snowpark_entry import run
    return json.loads(run(session, site_ids or "", triggered_by or "manual"))
$$;

-- Runs the pipeline for every site whose documents changed since the last call, and consumes the stream.
CREATE TABLE IF NOT EXISTS APP.PIPELINE_TRIGGER_LOG (TRIGGERED_AT TIMESTAMP_TZ, SITE_IDS VARCHAR, FILES NUMBER, RESULT VARIANT);

CREATE OR REPLACE PROCEDURE APP.SP_RUN_CHANGED_SITES()
  RETURNS VARIANT
  LANGUAGE SQL
  EXECUTE AS OWNER
AS
$$
DECLARE
  sites VARCHAR;
  files NUMBER;
  result VARIANT;
BEGIN
  CREATE OR REPLACE TEMPORARY TABLE APP.TMP_CHANGED AS
    SELECT RELATIVE_PATH,
           CASE WHEN STARTSWITH(RELATIVE_PATH, 'Input-Data/Sites/') THEN SPLIT_PART(RELATIVE_PATH, '/', 3)
                WHEN STARTSWITH(RELATIVE_PATH, 'uploads/') THEN SPLIT_PART(RELATIVE_PATH, '/', 2) END AS SITE_ID
    FROM RAW.SITE_DOCS_CHANGES;
  SELECT LISTAGG(DISTINCT SITE_ID, ',') WITHIN GROUP (ORDER BY SITE_ID), COUNT(*) INTO :sites, :files
    FROM APP.TMP_CHANGED WHERE SITE_ID IS NOT NULL;
  -- consume the stream (any DML that reads it advances the offset)
  INSERT INTO APP.PIPELINE_TRIGGER_LOG (TRIGGERED_AT, SITE_IDS, FILES)
    SELECT CURRENT_TIMESTAMP(), :sites, COUNT(*) FROM RAW.SITE_DOCS_CHANGES;
  IF (sites IS NULL OR sites = '') THEN
    RETURN OBJECT_CONSTRUCT('sites', ARRAY_CONSTRUCT(), 'message', 'no site documents changed');
  END IF;
  CALL APP.SP_RUN_PIPELINE(:sites, 'snowflake-task') INTO :result;
  UPDATE APP.PIPELINE_TRIGGER_LOG SET RESULT = :result WHERE SITE_IDS = :sites AND RESULT IS NULL;
  RETURN result;
END;
$$;

GRANT USAGE ON PROCEDURE APP.SP_RUN_PIPELINE(VARCHAR, VARCHAR) TO ROLE IDENTIFIER($SCOPEIQ_APP_ROLE);
GRANT USAGE ON PROCEDURE APP.SP_RUN_CHANGED_SITES() TO ROLE IDENTIFIER($SCOPEIQ_APP_ROLE);
EXECUTE IMMEDIATE 'ALTER PROCEDURE APP.SP_RUN_PIPELINE(VARCHAR, VARCHAR) SET LOG_LEVEL = ' || $SCOPEIQ_LOG_LEVEL;

-- Smoke test (one site; takes a minute on an XSMALL warehouse):
-- CALL APP.SP_RUN_PIPELINE('TXDA1024', CURRENT_USER());
