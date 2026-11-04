"""Safe site reset script for ScopeIQ.

Deletes site records and site-dependent pipeline data while PRESERVING:
  - REF.* (all reference tables: catalogs, rules, rates, users, etc.)
  - RAW.* (raw SiteTracker project/site references)
  - CORE.USER_LOGIN (all user sign-in accounts and hashed credentials)

Can target:
  - Snowflake (SCOPEIQ_DEV)
  - Local SQLite (code/output/scopeiq_local.db, including ScopeIQ2 if present)
  - Both (default: all)

Can also immediately create a new site (and optionally run the pipeline).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Add backend to sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from scopeiq.db.repository import get_repository, SqliteRepository, SnowflakeRepository
from scopeiq.db.repository import now_iso
from scopeiq.reference.loader import load_reference
from scopeiq.services.pipeline import PipelineService
from scopeiq.services.seed import ensure_reference_loaded

# Tables that store site data in deletion order (children first)
SITE_TABLES = [
    "CORE.REDLINE_PROOF",
    "CORE.REDLINE",
    "CORE.RFI",
    "CORE.BOM_CHANGE",
    "CORE.BOM_LINE",
    "CORE.BOM_REVISION",
    "CORE.DISCREPANCY",
    "CORE.EHS_ALERT",
    "CORE.EQUIPMENT_DELTA",
    "CORE.DRIVER_LINE",
    "CORE.SITE_REQUIREMENT",
    "CORE.ESTIMATE",
    "CORE.EVIDENCE_FRAME",
    "CORE.FIELD_OBJECT",
    "CORE.REV0_LINE",
    "CORE.ANALYSIS_RESULT",
    "CORE.TRUNK_MEASURE",
    "CORE.SECTOR_INFO",
    "CORE.CONFIG_LINE",
    "CORE.EXTRACTED_COMPARISON_RECORD",
    "CORE.EXTRACTED_FIELD",
    "CORE.PIPELINE_RUN",
    "CORE.UPLOAD",
    "CORE.DOCUMENT",
    "CORE.MILESTONE",
    "CORE.SITE",
    "WF.COMMENT",
    "WF.NOTIFICATION",
    "WF.WORKFLOW_EVENT",
]


def reset_sqlite_db(db_path: Path, site_id: str | None = None, dry_run: bool = False) -> dict[str, int]:
    """Delete site data from a SQLite database file."""
    if not db_path.exists():
        print(f"  [SQLite] Database not found at {db_path}, skipping.")
        return {}
    
    print(f"\n[SQLite] Connecting to {db_path}...")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    # Check existing tables
    existing_tables = set(r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    deleted_counts = {}
    
    for fqn in SITE_TABLES:
        phys = fqn.replace(".", "__")
        if phys not in existing_tables:
            continue
        
        if site_id:
            # Check if SITE_ID column exists in table
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info({phys})").fetchall()]
            if "SITE_ID" in cols:
                cur.execute(f"SELECT count(*) FROM {phys} WHERE SITE_ID = ?", (site_id,))
                cnt = cur.fetchone()[0]
                if cnt > 0:
                    deleted_counts[fqn] = cnt
                    if not dry_run:
                        cur.execute(f"DELETE FROM {phys} WHERE SITE_ID = ?", (site_id,))
        else:
            cur.execute(f"SELECT count(*) FROM {phys}")
            cnt = cur.fetchone()[0]
            if cnt > 0:
                deleted_counts[fqn] = cnt
                if not dry_run:
                    cur.execute(f"DELETE FROM {phys}")

    # Also clean up lost_and_found table if present
    if not site_id and "lost_and_found" in existing_tables:
        cnt = cur.execute("SELECT count(*) FROM lost_and_found").fetchone()[0]
        if cnt > 0:
            deleted_counts["lost_and_found"] = cnt
            if not dry_run:
                cur.execute("DELETE FROM lost_and_found")

    if not dry_run:
        conn.commit()
    conn.close()
    
    action = "Would delete" if dry_run else "Deleted"
    for tbl, count in deleted_counts.items():
        print(f"  {action} {count} rows from {tbl}")
    if not deleted_counts:
        print("  No matching site rows found.")
    return deleted_counts


def reset_snowflake(repo: SnowflakeRepository, site_id: str | None = None, dry_run: bool = False) -> dict[str, int]:
    """Delete site data from Snowflake SCOPEIQ_DEV."""
    print("\n[Snowflake] Resetting tables in Snowflake SCOPEIQ_DEV...")
    deleted_counts = {}
    
    for fqn in SITE_TABLES:
        try:
            if site_id:
                res = repo.query(f"SELECT count(*) as CNT FROM {fqn} WHERE SITE_ID = %s", [site_id])
                cnt = res[0]["CNT"] if res else 0
                if cnt > 0:
                    deleted_counts[fqn] = cnt
                    if not dry_run:
                        repo.execute(f"DELETE FROM {fqn} WHERE SITE_ID = %s", [site_id])
            else:
                res = repo.query(f"SELECT count(*) as CNT FROM {fqn}")
                cnt = res[0]["CNT"] if res else 0
                if cnt > 0:
                    deleted_counts[fqn] = cnt
                    if not dry_run:
                        # Use TRUNCATE or DELETE
                        repo.execute(f"TRUNCATE TABLE {fqn}")
        except Exception as e:
            # Table might be empty or missing in certain schemas
            pass

    action = "Would delete" if dry_run else "Deleted"
    for tbl, count in deleted_counts.items():
        print(f"  {action} {count} rows from {tbl}")
    if not deleted_counts:
        print("  No matching site rows found.")
    return deleted_counts


def create_new_site(repo, site_id: str, name: str, city: str, state: str, structure_type: str = "Monopole",
                    stream: str = "BOM", height_ft: float = 150.0) -> dict:
    """Create a brand new site record."""
    print(f"\n[Create Site] Creating site {site_id} ({name}, {city}, {state})...")
    row = {
        "SITE_ID": site_id,
        "SITE_NAME": name,
        "MARKET": "North Texas",
        "CUSTOMER": "Verizon",
        "ADDRESS": f"100 Main St, {city}, {state}",
        "CITY": city,
        "STATE": state,
        "ZIP": "75001",
        "LATITUDE": 32.7767,
        "LONGITUDE": -96.7970,
        "STRUCTURE_TYPE": structure_type,
        "HEIGHT_FT": height_ft,
        "SITE_STATUS": "New",
        "STREAM": stream,
        "WORKFLOW_STATE": "ASSIGNED",
        "ASSIGNED_DATE": now_iso()[:10],
        "UPDATED_AT": now_iso(),
        "UPDATED_BY": "admin",
    }
    repo.insert("CORE.SITE", [row])
    print(f"  Successfully inserted site {site_id} into CORE.SITE!")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", choices=["all", "snowflake", "sqlite"], default="all",
                        help="Database target to wipe (default: all)")
    parser.add_argument("--site-id", default=None,
                        help="Specific site ID to delete (if omitted, wipes ALL sites)")
    parser.add_argument("--create-site", default=None,
                        help="Create a new site after wipe (e.g. TXDA1024 or TXNW0001)")
    parser.add_argument("--name", default="Dallas North Tower", help="Name for new site")
    parser.add_argument("--city", default="Dallas", help="City for new site")
    parser.add_argument("--state", default="TX", help="State for new site")
    parser.add_argument("--run-pipeline", action="store_true",
                        help="Immediately execute the ScopeIQ pipeline on the newly created site")
    parser.add_argument("--clear-output-files", action="store_true",
                        help="Also delete generated files in code/output/sites/ and evidence/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate deletion and show counts without modifying data")
    args = parser.parse_args()

    print("=" * 60)
    print(" ScopeIQ Site Reset Tool")
    print("=" * 60)
    if args.dry_run:
        print("[DRY-RUN MODE] No changes will be committed.")

    # 1. Reset SQLite
    if args.target in ("all", "sqlite"):
        db_paths = [
            BACKEND_DIR.parent / "output" / "scopeiq_local.db",
            Path("/Users/adarshsharma/Documents/Projects/ScopeIQ2/ScopeIQ/code/output/scopeiq_local.db"),
        ]
        for dbp in db_paths:
            reset_sqlite_db(dbp, site_id=args.site_id, dry_run=args.dry_run)

    # 2. Reset Snowflake
    if args.target in ("all", "snowflake"):
        try:
            repo = get_repository()
            if isinstance(repo, SnowflakeRepository):
                reset_snowflake(repo, site_id=args.site_id, dry_run=args.dry_run)
            else:
                print(f"\n[Snowflake] Current repository is {type(repo).__name__}, not SnowflakeRepository.")
        except Exception as e:
            print(f"\n[Snowflake] Error connecting or resetting: {e}")

    # 3. Clear file outputs if requested
    if args.clear_output_files and not args.dry_run:
        print("\n[Files] Clearing generated site folders in code/output/sites/ and evidence/...")
        sites_dir = BACKEND_DIR.parent / "output" / "sites"
        evidence_dir = BACKEND_DIR.parent / "output" / "evidence"
        if sites_dir.exists():
            for item in sites_dir.iterdir():
                if item.is_dir() and (not args.site_id or item.name == args.site_id):
                    shutil.rmtree(item, ignore_errors=True)
                    print(f"  Removed {item}")
        if evidence_dir.exists():
            for item in evidence_dir.iterdir():
                if item.is_dir() and (not args.site_id or item.name == args.site_id):
                    shutil.rmtree(item, ignore_errors=True)
                    print(f"  Removed {item}")
        for sp_base in [
            BACKEND_DIR.parent / "output" / "sharepoint" / "Ericsson-Scoping" / "Sites",
            Path("/Users/adarshsharma/Documents/Projects/ScopeIQ2/ScopeIQ/code/output/sharepoint/Ericsson-Scoping/Sites"),
        ]:
            if sp_base.exists():
                for item in sp_base.iterdir():
                    if item.is_dir() and (not args.site_id or item.name == args.site_id):
                        shutil.rmtree(item, ignore_errors=True)
                        print(f"  Removed SharePoint folder {item}")

    # 4. Create new site if requested
    if args.create_site and not args.dry_run:
        new_sid = args.create_site.upper()
        # Create in SQLite and Snowflake
        if args.target in ("all", "sqlite"):
            for dbp in [BACKEND_DIR.parent / "output" / "scopeiq_local.db",
                        Path("/Users/adarshsharma/Documents/Projects/ScopeIQ2/ScopeIQ/code/output/scopeiq_local.db")]:
                if dbp.exists():
                    try:
                        sql_repo = SqliteRepository(dbp)
                        create_new_site(sql_repo, new_sid, args.name, args.city, args.state)
                    except Exception as e:
                        print(f"  Could not create in SQLite {dbp}: {e}")

        if args.target in ("all", "snowflake"):
            try:
                repo = get_repository()
                create_new_site(repo, new_sid, args.name, args.city, args.state)
            except Exception as e:
                print(f"  Could not create in Snowflake: {e}")

        # 5. Optionally run pipeline
        if args.run_pipeline:
            print(f"\n[Pipeline] Running ScopeIQ pipeline for {new_sid}...")
            try:
                p_repo = get_repository()
                ensure_reference_loaded(p_repo)
                p_ref = load_reference()
                svc = PipelineService(p_repo, p_ref)
                res = svc.run_site(new_sid, triggered_by="admin")
                summary = res.get("summary", {})
                print(f"  Pipeline completed successfully for {new_sid}!")
                print(f"  Discrepancies: {summary.get('discrepancies', 0)}")
                print(f"  Redlines: {summary.get('redlines', 0)}")
                print(f"  RFIs: {summary.get('rfis', 0)}")
            except Exception as e:
                print(f"  Pipeline execution error for {new_sid}: {e}")

    print("\n[Done] Site reset process complete.")


if __name__ == "__main__":
    main()
