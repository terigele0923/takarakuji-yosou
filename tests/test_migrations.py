import sqlite3
from pathlib import Path

from app.db_migrations import upgrade_database
from scripts.verify_database import REQUIRED_TABLES, verify_database


def test_upgrade_creates_expected_schema_and_is_idempotent(tmp_path):
    database_path = tmp_path / "migration.db"

    upgrade_database(database_path)
    upgrade_database(database_path)
    verify_database(database_path)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('purchases')")
        }

    assert REQUIRED_TABLES <= tables
    assert revision == "20261101_0005"
    assert "ix_purchases_pending" in indexes


def test_upgrade_preserves_database_created_before_alembic(tmp_path):
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE draws (
                lottery TEXT NOT NULL, round INTEGER NOT NULL,
                draw_date TEXT NOT NULL, numbers TEXT NOT NULL, bonus TEXT NOT NULL,
                PRIMARY KEY (lottery, round)
            );
            CREATE TABLE prizes (
                lottery TEXT NOT NULL, round INTEGER NOT NULL,
                tier TEXT NOT NULL, amount INTEGER NOT NULL,
                PRIMARY KEY (lottery, round, tier)
            );
            CREATE TABLE purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT, lottery TEXT NOT NULL,
                round INTEGER NOT NULL, numbers TEXT NOT NULL, play_type TEXT NOT NULL,
                price INTEGER NOT NULL, purchased_at TEXT NOT NULL, tier TEXT, prize INTEGER
            );
            """
        )
        connection.execute(
            "INSERT INTO draws VALUES (?, ?, ?, ?, ?)",
            ("loto6", 1, "2000-01-01", "1,2,3,4,5,6", "7"),
        )

    upgrade_database(database_path)

    with sqlite3.connect(database_path) as connection:
        saved_draw = connection.execute(
            "SELECT lottery, round, numbers FROM draws"
        ).fetchone()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]

    assert saved_draw == ("loto6", 1, "1,2,3,4,5,6")
    assert revision == "20261101_0005"


def test_upgrade_accepts_schema_precreated_by_test_sql(tmp_path):
    database_path = tmp_path / "precreated.db"
    schema_path = Path(__file__).parents[1] / "scripts" / "create_tables.sql"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))

    upgrade_database(database_path)
    verify_database(database_path)

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    assert revision == "20261101_0005"
