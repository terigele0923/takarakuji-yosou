"""Remove only walk-forward test purchases from the production ledger."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.walk_forward_purchase_import_service import (
    clear_walk_forward_purchases,
)

if __name__ == "__main__":
    result = clear_walk_forward_purchases()
    print(f"削除したテスト購入: {result.removed}件")
    if result.backup_path:
        print(f"バックアップ: {result.backup_path.resolve()}")
    print(
        f"現在の収支: {result.summary.count}件 / "
        f"支出 {result.summary.spent:,}円 / "
        f"賞金 {result.summary.won:,}円 / "
        f"差引 {result.summary.profit:,}円"
    )
