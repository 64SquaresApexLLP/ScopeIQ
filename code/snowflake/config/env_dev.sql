-- ScopeIQ DEV environment variables. Every numbered script starts from these (deploy_snowflake.py prepends this file).
-- Change values here, never inside the numbered scripts.
SET SCOPEIQ_ENV        = 'dev';                       -- passed to the Snowpark procedure (selects scopeiq/config/dev.yaml)
SET SCOPEIQ_DB         = 'SCOPEIQ_DEV';
SET SCOPEIQ_WH         = 'SCOPEIQ_DEV_WH';
SET SCOPEIQ_WH_SIZE    = 'XSMALL';
SET SCOPEIQ_ADMIN_ROLE = 'SCOPEIQ_DEV_ADMIN';       -- owns objects, runs deployments
SET SCOPEIQ_APP_ROLE   = 'SCOPEIQ_DEV_APP';         -- API / procedures: read-write CORE, WF, AUDIT; read REF, RAW
SET SCOPEIQ_READ_ROLE  = 'SCOPEIQ_DEV_READ';        -- analysts and dashboards: read-only views
SET SCOPEIQ_LOG_LEVEL  = 'DEBUG';                    -- Snowflake LOG_LEVEL for procedures (event table)
SET SCOPEIQ_TRACE_LEVEL= 'ALWAYS';
SET SCOPEIQ_APP_LOG_LEVEL = 'DEBUG';                 -- ScopeIQ logging.level override passed to the procedure
SET SCOPEIQ_TASK_SCHEDULE = 'USING CRON 0 */2 * * * America/Chicago';
