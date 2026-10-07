-- ScopeIQ PROD environment variables. Every numbered script starts from these (deploy_snowflake.py prepends this file).
-- Change values here, never inside the numbered scripts.
SET SCOPEIQ_ENV        = 'prod';                       -- passed to the Snowpark procedure (selects scopeiq/config/prod.yaml)
SET SCOPEIQ_DB         = 'SCOPEIQ_PROD';
SET SCOPEIQ_WH         = 'SCOPEIQ_PROD_WH';
SET SCOPEIQ_WH_SIZE    = 'SMALL';
SET SCOPEIQ_ADMIN_ROLE = 'SCOPEIQ_PROD_ADMIN';       -- owns objects, runs deployments
SET SCOPEIQ_APP_ROLE   = 'SCOPEIQ_PROD_APP';         -- API / procedures: read-write CORE, WF, AUDIT; read REF, RAW
SET SCOPEIQ_READ_ROLE  = 'SCOPEIQ_PROD_READ';        -- analysts and dashboards: read-only views
SET SCOPEIQ_LOG_LEVEL  = 'WARN';                    -- Snowflake LOG_LEVEL for procedures (event table)
SET SCOPEIQ_TRACE_LEVEL= 'OFF';
SET SCOPEIQ_APP_LOG_LEVEL = 'WARNING';                 -- ScopeIQ logging.level override passed to the procedure
SET SCOPEIQ_TASK_SCHEDULE = 'USING CRON 0 */2 * * * America/Chicago';
