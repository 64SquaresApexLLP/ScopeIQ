# ScopeIQ - Snowflake Streamlit demo

Branch `feat/snowflake-streamlit-demo`. Separate from the FastAPI app on `dev`.

## Files
- `streamlit_app.py` - the app (main file)
- `environment.yml` - packages (Snowflake Anaconda channel)
- `snowflake.yml` - Snowflake CLI deploy definition (`SCOPEIQ_DB.APP.SCOPEIQ_APP`, warehouse `SCOPEIQ_WH`)

## Deploy
From a Snowsight Workspace: open the workspace, connect it to this branch, then use Deploy/Run on `streamlit_app.py`.

From VS Code (CLI): `snow streamlit deploy` (never add `--replace` on an existing app without asking).

Rule: nothing is deleted or replaced in Snowflake without the owner's explicit say-so.
Connection secrets live in `~/.snowflake/config.toml`, never in this repo.
