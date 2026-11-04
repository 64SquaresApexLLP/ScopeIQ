"""Create the one admin login in the configured database (local SQLite by default). Run it once per database:
on your laptop before committing scopeiq_local.db, and once on the server (the server keeps its own database).

    python scripts/create_admin.py            # asks for the password twice
    python scripts/create_admin.py --reset    # sets a new password on the existing admin

The password is stored as a salted hash, never as text. Stop the backend first so the database is not in use.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scopeiq.common.errors import AppError  # noqa: E402
from scopeiq.db.repository import get_repository  # noqa: E402
from scopeiq.services.admin_account import admin_username, create_admin  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="set a new password on the existing admin login")
    args = ap.parse_args()

    password = input(f"Password for '{admin_username()}': ").strip()
    if password != input("Repeat the password: ").strip():
        print("The passwords do not match - nothing changed.")
        return 1
    try:
        row = create_admin(get_repository(), password, reset=args.reset)
    except AppError as exc:
        print(f"Not done: {exc}")
        return 1
    print(f"Admin login {'updated' if args.reset else 'created'}: username '{row['USERNAME']}'. Share the password with the team privately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
