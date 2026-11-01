"""Verify that a migrated SQLite database has the required schema."""

import argparse
import sqlite3
from pathlib import Path

REQUIRED_TABLES = {"alembic_version", "draws", "prizes", "purchases"}


def verify_database(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise RuntimeError(f"Missing database tables: {sorted(missing)}")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite quick_check failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database_path", type=Path)
    arguments = parser.parse_args()
    verify_database(arguments.database_path)
