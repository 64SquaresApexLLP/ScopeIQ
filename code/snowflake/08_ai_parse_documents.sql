-- =====================================================================================================
-- 08  Layout-aware parsing of staged PDFs with AI_PARSE_DOCUMENT (Cortex). Results are kept in
--     RAW.DOC_PARSE for reviewers and for CDs that exist only as scanned PDFs: the Snowpark procedure has
--     no Tesseract, so in Snowflake those CDs are read here (or by the SPCS job, EXECUTION_GUIDE section 7).
--     Incremental: only files not parsed yet (or changed since) are sent to the function.
-- =====================================================================================================
USE ROLE IDENTIFIER($SCOPEIQ_ADMIN_ROLE);
USE DATABASE IDENTIFIER($SCOPEIQ_DB);
USE WAREHOUSE IDENTIFIER($SCOPEIQ_WH);

CREATE TABLE IF NOT EXISTS RAW.DOC_PARSE (
  RELATIVE_PATH VARCHAR NOT NULL, SITE_ID VARCHAR, DOC_TYPE VARCHAR, MD5 VARCHAR, PARSE_MODE VARCHAR,
  PARSED VARIANT, PARSED_AT TIMESTAMP_TZ, ERROR VARCHAR,
  CONSTRAINT PK_DOC_PARSE PRIMARY KEY (RELATIVE_PATH, PARSE_MODE)
) COMMENT = 'AI_PARSE_DOCUMENT output per staged PDF';

INSERT INTO RAW.DOC_PARSE (RELATIVE_PATH, SITE_ID, DOC_TYPE, MD5, PARSE_MODE, PARSED, PARSED_AT)
SELECT f.RELATIVE_PATH, f.SITE_ID, f.DOC_TYPE, f.MD5, 'LAYOUT',
       AI_PARSE_DOCUMENT(TO_FILE('@RAW.SITE_DOCS', f.RELATIVE_PATH), {'mode': 'LAYOUT', 'page_split': true}),
       CURRENT_TIMESTAMP()
FROM RAW.FILE_REGISTRY f
LEFT JOIN RAW.DOC_PARSE d ON d.RELATIVE_PATH = f.RELATIVE_PATH AND d.PARSE_MODE = 'LAYOUT' AND d.MD5 = f.MD5
WHERE f.FILE_FORMAT = 'PDF' AND f.DOC_TYPE IN ('CD', 'RFDS', 'MA_SA') AND d.RELATIVE_PATH IS NULL;

-- One row per page with its markdown text
CREATE OR REPLACE VIEW RAW.V_DOC_PARSE_PAGES AS
SELECT d.SITE_ID, d.DOC_TYPE, d.RELATIVE_PATH, p.INDEX + 1 AS PAGE_NO, p.VALUE:content::VARCHAR AS PAGE_TEXT, d.PARSED_AT
FROM RAW.DOC_PARSE d, LATERAL FLATTEN(INPUT => d.PARSED:pages) p
WHERE d.PARSE_MODE = 'LAYOUT';

-- Example: the CD sheet that carries the antenna schedule (A-3) for each site
SELECT SITE_ID, RELATIVE_PATH, PAGE_NO, LEFT(PAGE_TEXT, 400) AS PREVIEW
FROM RAW.V_DOC_PARSE_PAGES WHERE DOC_TYPE = 'CD' AND PAGE_TEXT ILIKE '%ANTENNA%SCHEDULE%' ORDER BY SITE_ID, PAGE_NO;
