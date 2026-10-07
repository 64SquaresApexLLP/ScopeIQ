-- =====================================================================================================
-- 12  Logging per environment and monitoring.
--     Two layers, both controlled outside the code:
--       * ScopeIQ application logging: logging.* in scopeiq/config/<env>.yaml, overridable with
--         SCOPEIQ__LOGGING__LEVEL etc.; in Snowflake the procedure takes APP_LOG_LEVEL from APP.SETTINGS.
--         WARNING+ (INFO+ in dev/test) lands in AUDIT.APP_LOG, errors with stack in AUDIT.ERROR_LOG.
--       * Snowflake LOG_LEVEL / TRACE_LEVEL on the database (set in 01 from config/env_<env>.sql) route
--         procedure stdout/logging into an event table.
-- =====================================================================================================
USE ROLE IDENTIFIER($SCOPEIQ_ADMIN_ROLE);
USE DATABASE IDENTIFIER($SCOPEIQ_DB);
USE WAREHOUSE IDENTIFIER($SCOPEIQ_WH);

CREATE EVENT TABLE IF NOT EXISTS AUDIT.SCOPEIQ_EVENTS COMMENT = 'Snowflake telemetry for ScopeIQ procedures';
USE ROLE ACCOUNTADMIN;
EXECUTE IMMEDIATE 'ALTER DATABASE ' || $SCOPEIQ_DB || ' SET EVENT_TABLE = ' || $SCOPEIQ_DB || '.AUDIT.SCOPEIQ_EVENTS';
USE ROLE IDENTIFIER($SCOPEIQ_ADMIN_ROLE);

-- Change the level later without redeploying:
--   UPDATE APP.SETTINGS SET VALUE = 'DEBUG' WHERE KEY = 'APP_LOG_LEVEL';           -- ScopeIQ logger
--   ALTER PROCEDURE APP.SP_RUN_PIPELINE(VARCHAR, VARCHAR) SET LOG_LEVEL = 'DEBUG';  -- Snowflake event table

CREATE OR REPLACE VIEW APP.V_PROCEDURE_LOGS AS
SELECT TIMESTAMP, RECORD:severity_text::VARCHAR AS LEVEL, RESOURCE_ATTRIBUTES:"snow.executable.name"::VARCHAR AS EXECUTABLE,
       SCOPE:name::VARCHAR AS LOGGER, VALUE::VARCHAR AS MESSAGE
FROM AUDIT.SCOPEIQ_EVENTS WHERE RECORD_TYPE = 'LOG';

CREATE OR REPLACE VIEW APP.V_PIPELINE_HEALTH AS
SELECT DATE_TRUNC(day, STARTED_AT) AS RUN_DAY, STATUS, COUNT(*) AS RUNS,
       AVG(DATEDIFF(second, STARTED_AT, FINISHED_AT)) AS AVG_SECONDS, ARRAY_AGG(DISTINCT SITE_ID) AS SITES
FROM CORE.PIPELINE_RUN GROUP BY ALL;

-- Optional alert on failed runs (needs an email notification integration named SCOPEIQ_EMAIL):
-- CREATE OR REPLACE ALERT APP.A_PIPELINE_FAILED WAREHOUSE = SCOPEIQ_DEV_WH SCHEDULE = '60 MINUTE'
--   IF (EXISTS (SELECT 1 FROM CORE.PIPELINE_RUN WHERE STATUS = 'FAILED' AND STARTED_AT > DATEADD(hour, -1, CURRENT_TIMESTAMP())))
--   THEN CALL SYSTEM$SEND_EMAIL('SCOPEIQ_EMAIL', 'scoping-leads@example.com', 'ScopeIQ pipeline failure', 'See APP.V_ERRORS_24H');
-- ALTER ALERT APP.A_PIPELINE_FAILED RESUME;
