"""Import a walk-forward report into the production purchase ledger."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.walk_forward_purchase_import_service import (
    import_walk_forward_report,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--numbers3-tickets", type=int, default=5)
    parser.add_argument("--replace-existing", action="store_true")
    arguments = parser.parse_args()
    result = import_walk_forward_report(
        arguments.report,
        numbers3_tickets=arguments.numbers3_tickets,
        replace_existing=arguments.replace_existing,
    )
    print(f"追加: {result.added}件 / 登録済み: {result.skipped}件")
    print(f"結果判定: {result.checked}件")
    if result.backup_path:
        print(f"バックアップ: {result.backup_path.resolve()}")
    print(
        f"収支: 支出 {result.summary.spent:,}円 / "
        f"賞金 {result.summary.won:,}円 / "
        f"差引 {result.summary.profit:,}円"
    )
