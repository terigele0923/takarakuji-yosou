import sqlite3

from app.services.database_maintenance_service import cleanup_database_versions


def test_本番とサンプルを残して旧DBだけ整理する(tmp_path):
    database_path = tmp_path / "lottery.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES ('production')")

    sample_path = tmp_path / "sample.db"
    sample_path.write_bytes(b"sample")
    obsolete_paths = [
        tmp_path / "lottery.backup-20260101.db",
        tmp_path / "lottery.backup-before-walk-forward-20260102.db",
        tmp_path / "lottery.before-history-20260103.db",
        tmp_path / "walk_forward_mock-20260104.db",
        tmp_path / "lottery.production-backup-20260105.db",
    ]
    for path in obsolete_paths:
        path.write_bytes(b"old")

    result = cleanup_database_versions(database_path)

    assert result.backup_path.exists()
    assert len(result.removed_paths) == len(obsolete_paths)
    assert database_path.exists()
    assert sample_path.read_bytes() == b"sample"
    assert not any(path.exists() for path in obsolete_paths)
    with sqlite3.connect(result.backup_path) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == (
            "production",
        )
