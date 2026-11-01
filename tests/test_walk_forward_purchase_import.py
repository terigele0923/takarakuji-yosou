import datetime
import json
import sqlite3

from app.db_migrations import upgrade_database
from app.services.walk_forward_purchase_import_service import (
    clear_walk_forward_purchases,
    import_walk_forward_report,
)


def test_評価レポートを収支へ一度だけ反映して当選判定する(tmp_path):
    database_path = tmp_path / "lottery.db"
    report_path = tmp_path / "report.json"
    upgrade_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO draws VALUES (?, ?, ?, ?, ?)",
            ("loto6", 1, "2026-01-01", "1,2,3,4,5,6", "7"),
        )
        connection.execute(
            "INSERT INTO prizes VALUES (?, ?, ?, ?)",
            ("loto6", 1, "5等", 1_000),
        )
        connection.execute(
            "INSERT INTO draws VALUES (?, ?, ?, ?, ?)",
            ("numbers3", 1, "2026-01-01", "1,2,3", ""),
        )
        connection.execute(
            "INSERT INTO prizes VALUES (?, ?, ?, ?)",
            ("numbers3", 1, "ストレート", 10_000),
        )
    report_path.write_text(
        json.dumps(
            {
                "source_database": str(database_path.resolve()),
                "generated_at": datetime.datetime.now().astimezone().isoformat(),
                "steps": [
                    {
                        "lottery": "loto6",
                        "round": 1,
                        "predicted_numbers": [[1, 2, 3, 20, 21, 22]],
                    },
                    {
                        "lottery": "numbers3",
                        "round": 1,
                        "predicted_numbers": [[1, 2, 3]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    first = import_walk_forward_report(report_path, database_path)
    repeated = import_walk_forward_report(report_path, database_path)

    assert first.added == 6
    assert first.checked == 6
    assert first.backup_path is not None and first.backup_path.exists()
    assert first.summary.spent == 1_200
    assert first.summary.won == 51_000
    assert first.summary.profit == 49_800
    assert repeated.added == 0
    assert repeated.skipped == 6
    assert repeated.backup_path is None

    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["steps"] = [report["steps"][1]]
    report_path.write_text(json.dumps(report), encoding="utf-8")
    replaced = import_walk_forward_report(
        report_path,
        database_path,
        numbers3_tickets=5,
        replace_existing=True,
    )
    assert replaced.added == 5
    assert replaced.summary.count == 5
    assert replaced.summary.spent == 1_000
    assert replaced.summary.won == 50_000

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO purchases (
                lottery, round, numbers, play_type, price, purchased_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("loto6", 2, "1,2,3,4,5,6", "normal", 200, "2026-01-01T00:00:00"),
        )

    cleared = clear_walk_forward_purchases(database_path)

    assert cleared.removed == 5
    assert cleared.backup_path is not None and cleared.backup_path.exists()
    assert cleared.summary.count == 1
    assert cleared.summary.spent == 200
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM purchase_imports").fetchone()[0] == 0
