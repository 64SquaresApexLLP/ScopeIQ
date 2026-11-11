-- Lets the Streamlit app reach Microsoft Graph (SharePoint). Additive only: IF NOT EXISTS, nothing dropped or replaced.
-- The secret VALUES are not in this file: scripts/store_secrets.py creates them from the local .env (never printed, never committed).
USE DATABASE SCOPEIQ_DB;
USE SCHEMA APP;

CREATE NETWORK RULE IF NOT EXISTS SCOPEIQ_DB.APP.MS_GRAPH_RULE
  MODE = EGRESS TYPE = HOST_PORT
  VALUE_LIST = ('login.microsoftonline.com:443', 'graph.microsoft.com:443')
  COMMENT = 'Microsoft sign-in and Graph only';

-- run scripts/store_secrets.py before this statement: it creates MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET, SHAREPOINT_SITE_URL
CREATE EXTERNAL ACCESS INTEGRATION IF NOT EXISTS SCOPEIQ_MS_GRAPH
  ALLOWED_NETWORK_RULES = (SCOPEIQ_DB.APP.MS_GRAPH_RULE)
  ALLOWED_AUTHENTICATION_SECRETS = (SCOPEIQ_DB.APP.MS_TENANT_ID, SCOPEIQ_DB.APP.MS_CLIENT_ID, SCOPEIQ_DB.APP.MS_CLIENT_SECRET, SCOPEIQ_DB.APP.SHAREPOINT_SITE_URL)
  ENABLED = TRUE
  COMMENT = 'ScopeIQ app -> Microsoft Graph';

-- attach to the app (changes the app's settings; does not recreate it)
ALTER STREAMLIT SCOPEIQ_DB.APP.SCOPEIQ_APP SET
  EXTERNAL_ACCESS_INTEGRATIONS = (SCOPEIQ_MS_GRAPH),
  SECRETS = ('ms_tenant_id' = SCOPEIQ_DB.APP.MS_TENANT_ID, 'ms_client_id' = SCOPEIQ_DB.APP.MS_CLIENT_ID,
             'ms_client_secret' = SCOPEIQ_DB.APP.MS_CLIENT_SECRET, 'sharepoint_site_url' = SCOPEIQ_DB.APP.SHAREPOINT_SITE_URL);
