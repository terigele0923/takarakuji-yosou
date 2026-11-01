"""Database backup retention and generated test artifact cleanup."""

from __future__ import annotations

import datetime
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.config import DB_PATH


@dataclass(frozen=True)
class DatabaseCleanupResult:
    backup_path: Path
    removed_paths: tuple[Path, ...]


def cleanup_database_versions(db_path: Path = DB_PATH) -> DatabaseCleanupResult:
    """Keep one verified production backup and remove obsolete generated DBs."""
    db_path = db_path.resolve()
    data_dir = db_path.parent
    timestamp = datetime.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = data_dir / f"{db_path.stem}.production-backup-{timestamp}.db"

    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()
    if integrity != ("ok",):
        backup_path.unlink(missing_ok=True)
        raise RuntimeError("作成したDBバックアップの整合性を確認できませんでした。")

    removal_candidates: set[Path] = set()
    for pattern in (
        f"{db_path.stem}.backup*.db",
        f"{db_path.stem}.before-history-*.db",
        "walk_forward_mock-*.db",
    ):
        removal_candidates.update(data_dir.glob(pattern))
    removal_candidates.update(
        path
        for path in data_dir.glob(f"{db_path.stem}.production-backup-*.db")
        if path != backup_path
    )

    removed_paths: list[Path] = []
    for path in sorted(removal_candidates):
        resolved = path.resolve()
        if resolved.parent != data_dir or resolved in {db_path, backup_path}:
            raise RuntimeError(f"削除対象がデータディレクトリ外です: {resolved}")
        resolved.unlink()
        removed_paths.append(resolved)

    return DatabaseCleanupResult(
        backup_path=backup_path,
        removed_paths=tuple(removed_paths),
    )
