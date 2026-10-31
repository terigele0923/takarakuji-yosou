"""Validate or import official CSV bundles collected by mizuho_collect.js."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_DB_PATH
from app.schemas.lottery import LotteryType
from app.services.mizuho_import_service import (
    ParsedDraw,
    apply_records,
    compare_database,
    deduplicate_records,
    parse_bundle,
)


def load_bundle(path: Path) -> list[ParsedDraw]:
    """1ファイルまたはフォルダー内の収集JSONを読み込む。"""
    bundle_files = [path] if path.is_file() else sorted(path.glob("*.json"))
    if not bundle_files:
        raise ValueError(f"No JSON bundles found in {path}")
    records = []
    for bundle_path in bundle_files:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        records.extend(parse_bundle(payload))
    return deduplicate_records(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate or import Mizuho official lottery CSV bundles"
    )
    parser.add_argument("bundle", type=Path, help="Downloaded JSON bundle, or a folder")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Target SQLite DB")
    parser.add_argument("--apply", action="store_true", help="Backup and write records")
    args = parser.parse_args()

    records = load_bundle(args.bundle)
    summary, conflicts = compare_database(args.db, records)
    print("Source: Mizuho official per-draw CSVs")
    print(f"Database: {args.db.resolve()}")
    print(f"Parsed draws: {len(records)}")
    for lottery in LotteryType:
        count = sum(record.lottery == lottery for record in records)
        if count:
            print(f"{lottery.value}: {count} draws")
    print(f"New draws: {summary['new_draws']}; existing draws: {summary['existing_draws']}")
    print(
        f"New prize rows: {summary['new_prizes']}; "
        f"existing prize rows: {summary['existing_prizes']}"
    )
    if conflicts:
        print(f"Conflicts: {len(conflicts)}")
        for conflict in conflicts[:20]:
            print(f"  - {conflict}")
        raise SystemExit(1)
    if not args.apply:
        print("Dry run only. Add --apply after reviewing the counts.")
        return
    backup_path = apply_records(args.db, records)
    print(f"Imported successfully. Backup: {backup_path.resolve()}")


if __name__ == "__main__":
    main()
