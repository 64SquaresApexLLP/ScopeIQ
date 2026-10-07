-- =====================================================================================================
-- 99  Teardown of one environment. DESTRUCTIVE: drops the database (all data), warehouse and roles.
--     Guarded: set CONFIRM_TEARDOWN to the database name first, e.g.  SET CONFIRM_TEARDOWN = 'SCOPEIQ_DEV';
-- =====================================================================================================
-- (Running without setting it fails with 'Session variable $CONFIRM_TEARDOWN does not exist', which is the guard.)
EXECUTE IMMEDIATE $$
BEGIN
  IF ($CONFIRM_TEARDOWN != $SCOPEIQ_DB) THEN
    RETURN 'Not confirmed: SET CONFIRM_TEARDOWN = ''' || $SCOPEIQ_DB || ''' and run again.';
  END IF;
  DROP DATABASE IF EXISTS IDENTIFIER($SCOPEIQ_DB);
  DROP WAREHOUSE IF EXISTS IDENTIFIER($SCOPEIQ_WH);
  DROP ROLE IF EXISTS IDENTIFIER($SCOPEIQ_READ_ROLE);
  DROP ROLE IF EXISTS IDENTIFIER($SCOPEIQ_APP_ROLE);
  DROP ROLE IF EXISTS IDENTIFIER($SCOPEIQ_ADMIN_ROLE);
  RETURN 'Dropped ' || $SCOPEIQ_DB;
END;
$$;
