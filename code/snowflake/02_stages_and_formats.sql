-- =====================================================================================================
-- 02  Stages, file formats and the file registry.   Revised from Data/DataDetails/snowflake_load.sql:
--     * the stage mirrors the ScopeIQ-POC/Data folder (Input-Data/Sites/<SITE>/..., Input-Data/SiteTracker/,
--       Reference-Data/) so local runs and Snowflake runs read identical paths,
--     * app uploads land under uploads/<SITE>/<folder>/ and take part in revision resolution,
--     * a CODE stage holds the scopeiq package and reference CSVs, an OUTPUT stage the generated files,
--     * FILE_REGISTRY classifies each file exactly like scopeiq/extract/registry.py.
-- =====================================================================================================
USE ROLE IDENTIFIER($SCOPEIQ_ADMIN_ROLE);
USE DATABASE IDENTIFIER($SCOPEIQ_DB);
USE WAREHOUSE IDENTIFIER($SCOPEIQ_WH);
USE SCHEMA RAW;

-- Server-side encryption lets AI_PARSE_DOCUMENT read staged PDFs.
CREATE STAGE IF NOT EXISTS SITE_DOCS     DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') COMMENT = 'Site documents, SiteTracker exports, uploads';
CREATE STAGE IF NOT EXISTS SCOPEIQ_CODE  DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') COMMENT = 'scopeiq_code.zip and reference_data/*.csv';
CREATE STAGE IF NOT EXISTS SCOPEIQ_OUTPUT DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') COMMENT = 'Generated BOM workbooks, redlined CDs, packages, evidence frames';
CREATE STAGE IF NOT EXISTS SEED          ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') COMMENT = 'Pipeline results exported from a local run (11_load_pipeline_results.sql)';

-- Upload (from a machine with the Snowflake CLI, in the ScopeIQ-POC folder):
--   snow stage copy "Data/Input-Data"     @<DB>.RAW.SITE_DOCS/Input-Data --recursive
--   snow stage copy "Data/Reference-Data" @<DB>.RAW.SITE_DOCS/Reference-Data --recursive
--   snow stage copy code/reference_data   @<DB>.RAW.SCOPEIQ_CODE/reference_data --recursive
--   snow stage copy code/dist/scopeiq_code.zip @<DB>.RAW.SCOPEIQ_CODE/
-- (deploy_snowflake.py --upload does all four.)
ALTER STAGE SITE_DOCS REFRESH;
ALTER STAGE SCOPEIQ_CODE REFRESH;

CREATE FILE FORMAT IF NOT EXISTS CSV_SKIP_HEADER TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE NULL_IF = ('') ENCODING = 'UTF8' COMMENT = 'Reference and SiteTracker CSVs';
CREATE FILE FORMAT IF NOT EXISTS NDJSON TYPE = JSON STRIP_OUTER_ARRAY = FALSE COMMENT = 'Pipeline result exports';

-- File registry: one row per staged file with site, area and document type.
CREATE OR REPLACE VIEW FILE_REGISTRY AS
WITH f AS (
  SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED, MD5, FILE_URL,
         CASE WHEN STARTSWITH(RELATIVE_PATH, 'Input-Data/Sites/') THEN 'SITE'
              WHEN STARTSWITH(RELATIVE_PATH, 'uploads/')          THEN 'UPLOAD'
              WHEN STARTSWITH(RELATIVE_PATH, 'Input-Data/SiteTracker/') THEN 'SITETRACKER'
              WHEN STARTSWITH(RELATIVE_PATH, 'Reference-Data/')   THEN 'REFERENCE' ELSE 'OTHER' END AS AREA,
         LOWER(RELATIVE_PATH) AS P,
         REGEXP_SUBSTR(RELATIVE_PATH, '[^/]+$') AS FILE_NAME
  FROM DIRECTORY(@SITE_DOCS)
)
SELECT RELATIVE_PATH, AREA, FILE_NAME,
       CASE AREA WHEN 'SITE' THEN SPLIT_PART(RELATIVE_PATH, '/', 3) WHEN 'UPLOAD' THEN SPLIT_PART(RELATIVE_PATH, '/', 2) END AS SITE_ID,
       CASE AREA WHEN 'SITE' THEN SPLIT_PART(RELATIVE_PATH, '/', 4) WHEN 'UPLOAD' THEN SPLIT_PART(RELATIVE_PATH, '/', 3) END AS DOC_FOLDER,
       CASE
         WHEN AREA NOT IN ('SITE', 'UPLOAD') THEN NULL
         WHEN P LIKE '%/rfds/%'  AND REGEXP_LIKE(FILE_NAME, '.*RFDS.*', 'i')       THEN 'RFDS'
         WHEN P LIKE '%/cds/%'   AND REGEXP_LIKE(FILE_NAME, '.*_P?CD_.*', 'i')     THEN 'CD'
         WHEN P LIKE '%/ma_sa/%' AND REGEXP_LIKE(FILE_NAME, '.*(MA|SA).*', 'i')    THEN 'MA_SA'
         WHEN P LIKE '%/bom/%'   AND REGEXP_LIKE(FILE_NAME, '.*BOM.*', 'i')        THEN 'BOM_REV0'
         WHEN P LIKE '%/drone/%' AND ENDSWITH(P, 'capture_metadata.json')          THEN 'DRONE_META'
         WHEN P LIKE '%/drone/%' AND ENDSWITH(P, 'vendor_measurements.csv')        THEN 'DRONE_VENDOR'
         WHEN P LIKE '%/drone/%' AND REGEXP_LIKE(P, '.*\\.la[sz]$')                THEN 'DRONE_POINTCLOUD'
         WHEN P LIKE '%/drone/%' AND REGEXP_LIKE(P, '.*\\.(jpe?g|png|tif)$')       THEN 'DRONE_IMAGE'
         WHEN P LIKE '%/drone/%' AND REGEXP_LIKE(P, '.*\\.(mp4|mov|avi)$')         THEN 'DRONE_VIDEO'
       END AS DOC_TYPE,
       COALESCE(REGEXP_SUBSTR(FILE_NAME, '_R(\\d+)[_.]', 1, 1, 'ie', 1), REGEXP_SUBSTR(FILE_NAME, '_REV ?(\\d+)', 1, 1, 'ie', 1)) AS REVISION_NO,
       UPPER(REGEXP_SUBSTR(FILE_NAME, '[^.]+$')) AS FILE_FORMAT,
       SIZE, LAST_MODIFIED, MD5, FILE_URL
FROM f;

-- Change stream on the stage directory: new or replaced files trigger the pipeline task (09_tasks.sql).
CREATE STREAM IF NOT EXISTS SITE_DOCS_CHANGES ON STAGE SITE_DOCS COMMENT = 'New / changed site documents';
