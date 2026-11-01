import datetime
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.config import DB_PATH
from app.schemas.lottery import RULES, LotteryType, PlayType
from app.schemas.purchase import PurchaseSummary
from app.services.lottery_data import validate_numbers
from app.services.purchase_service import check_results, list_purchases
from app.utils.number_codec import encode_numbers


@dataclass(frozen=True)
class WalkForwardImportResult:
    added: int
    skipped: int
    checked: int
    backup_path: Path | None
    summary: PurchaseSummary


@dataclass(frozen=True)
class ClearWalkForwardResult:
    removed: int
    backup_path: Path | None
    summary: PurchaseSummary


def import_walk_forward_report(
    report_path: Path,
    db_path: Path = DB_PATH,
    numbers3_tickets: int = 5,
    replace_existing: bool = False,
) -> WalkForwardImportResult:
    """ウォークフォワード予想を購入履歴へ一度だけ登録し、結果を判定する。"""
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes.decode("utf-8"))
    _validate_report(report, db_path)
    digest = hashlib.sha256(report_bytes).hexdigest()
    if numbers3_tickets <= 0:
        raise ValueError("ナンバーズ3の口数は正数で指定してください")
    candidates = _candidate_rows(report, digest, numbers3_tickets)

    with sqlite3.connect(db_path) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT source_ref FROM purchase_imports WHERE source_ref LIKE ?",
                (f"walk-forward:{digest}:%",),
            )
        }
    pending = candidates if replace_existing else [row for row in candidates if row[0] not in existing]
    if not pending:
        return WalkForwardImportResult(
            added=0,
            skipped=len(candidates),
            checked=0,
            backup_path=None,
            summary=list_purchases(db_path).summary,
        )

    backup_path = _backup_database(db_path)
    imported_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as connection:
        if replace_existing:
            connection.execute(
                "DELETE FROM purchases WHERE id IN "
                "(SELECT purchase_id FROM purchase_imports)"
            )
            connection.execute("DELETE FROM purchase_imports")
        for source_ref, lottery, round_number, numbers, play_type, purchased_at in pending:
            cursor = connection.execute(
                """
                INSERT INTO purchases (
                    lottery, round, numbers, play_type, price, purchased_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    lottery.value,
                    round_number,
                    encode_numbers(numbers),
                    play_type.value,
                    RULES[lottery].price,
                    purchased_at,
                ),
            )
            connection.execute(
                "INSERT INTO purchase_imports (source_ref, purchase_id, imported_at) "
                "VALUES (?, ?, ?)",
                (source_ref, cursor.lastrowid, imported_at),
            )

    checked = check_results(db_path)
    return WalkForwardImportResult(
        added=len(pending),
        skipped=0 if replace_existing else len(candidates) - len(pending),
        checked=checked.checked_count,
        backup_path=backup_path,
        summary=checked.summary,
    )


def clear_walk_forward_purchases(
    db_path: Path = DB_PATH,
) -> ClearWalkForwardResult:
    """テストレポート由来の購入だけを削除し、通常購入は保持する。"""
    with sqlite3.connect(db_path) as connection:
        purchase_ids = [
            row[0]
            for row in connection.execute(
                "SELECT purchase_id FROM purchase_imports ORDER BY purchase_id"
            )
        ]
    if not purchase_ids:
        return ClearWalkForwardResult(
            removed=0,
            backup_path=None,
            summary=list_purchases(db_path).summary,
        )

    backup_path = _backup_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM purchase_imports")
        connection.executemany(
            "DELETE FROM purchases WHERE id = ?",
            [(purchase_id,) for purchase_id in purchase_ids],
        )
    return ClearWalkForwardResult(
        removed=len(purchase_ids),
        backup_path=backup_path,
        summary=list_purchases(db_path).summary,
    )


def _candidate_rows(
    report: dict, digest: str, numbers3_tickets: int
) -> list[tuple]:
    purchased_at = report["generated_at"]
    rows = []
    for step in report["steps"]:
        lottery = LotteryType(step["lottery"])
        play_type = PlayType.STRAIGHT if RULES[lottery].by_position else PlayType.NORMAL
        predictions = step["predicted_numbers"]
        ticket_count = (
            numbers3_tickets
            if lottery == LotteryType.NUMBERS3
            else len(predictions)
        )
        for ticket_number in range(1, ticket_count + 1):
            raw_numbers = predictions[(ticket_number - 1) % len(predictions)]
            numbers = list(raw_numbers)
            validate_numbers(lottery, numbers)
            if not RULES[lottery].by_position:
                numbers.sort()
            source_ref = (
                f"walk-forward:{digest}:{lottery.value}:{step['round']}:{ticket_number}"
            )
            rows.append(
                (
                    source_ref,
                    lottery,
                    int(step["round"]),
                    numbers,
                    play_type,
                    purchased_at,
                )
            )
    return rows


def _validate_report(report: dict, db_path: Path) -> None:
    required = {"source_database", "generated_at", "steps"}
    if not required <= report.keys():
        raise ValueError("ウォークフォワード評価レポートの形式が正しくありません")
    if Path(report["source_database"]).resolve() != db_path.resolve():
        raise ValueError("このレポートを作成した実DBと、取込先DBが一致しません")


def _backup_database(db_path: Path) -> Path:
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(
        f"{db_path.stem}.backup-before-walk-forward-{timestamp}{db_path.suffix}"
    )
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    return backup_path
