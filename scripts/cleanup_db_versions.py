"""Create one clean production backup and remove obsolete generated databases."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.database_maintenance_service import cleanup_database_versions

if __name__ == "__main__":
    result = cleanup_database_versions()
    print(f"保持する本番バックアップ: {result.backup_path.resolve()}")
    print(f"削除した旧DB: {len(result.removed_paths)}件")
    for removed_path in result.removed_paths:
        print(f"  - {removed_path.name}")
