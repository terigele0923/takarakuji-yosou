import csv
import datetime as dt
import re
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.schemas.lottery import Draw, LotteryType
from app.services.lottery_data import validate_draw
from app.utils.number_codec import encode_numbers

LOTTERIES_BY_FAMILY = {
    "numbers": (LotteryType.NUMBERS3, LotteryType.NUMBERS4),
    "miniloto": (LotteryType.MINILOTO,),
    "loto6": (LotteryType.LOTO6,),
    "loto7": (LotteryType.LOTO7,),
}
ERA_BASES = {"令和": 2018, "平成": 1988, "昭和": 1925}
NUMBERS_PRIZE_NAMES = {
    "ストレート": "ストレート",
    "ボックス": "ボックス",
    "セット(ストレート)": "セット・ストレート",
    "セット(ボックス)": "セット・ボックス",
    "ミニ": "ミニ",
}


@dataclass(frozen=True)
class ParsedDraw:
    lottery: LotteryType
    draw: Draw
    prizes: dict[str, int]


def parse_mizuho_csv(family: str, text: str) -> list[ParsedDraw]:
    """みずほ銀行の1回分CSVを検査し、抽せん結果と賞金へ変換する。"""
    if family not in LOTTERIES_BY_FAMILY:
        raise ValueError(f"Unknown Mizuho CSV family: {family}")

    rows = [[field.strip() for field in row] for row in csv.reader(text.splitlines())]
    rows = [row for row in rows if row]
    if len(rows) < 2:
        raise ValueError("CSV is missing its draw header")

    header = rows[1]
    round_match = re.search(r"第\s*0*(\d+)\s*回", header[0])
    if not round_match or len(header) < 3:
        raise ValueError("CSV draw number or date is missing")
    round_number = int(round_match.group(1))
    draw_date = _parse_japanese_date(header[2])

    if family == "numbers":
        results = []
        for lottery, marker in (
            (LotteryType.NUMBERS3, "ナンバーズ３抽せん数字"),
            (LotteryType.NUMBERS4, "ナンバーズ４抽せん数字"),
        ):
            number_row = next((row for row in rows if row[0] == marker), None)
            if number_row is None or len(number_row) < 2:
                raise ValueError(f"{marker} is missing")
            digit_text = "".join(number_row[1:])
            if not digit_text.isdigit():
                raise ValueError(f"Invalid {marker}: {digit_text}")
            draw = Draw(
                round=round_number,
                draw_date=draw_date,
                numbers=[int(digit) for digit in digit_text],
                bonus=[],
            )
            validate_draw(lottery, draw)
            results.append(ParsedDraw(lottery, draw, _parse_numbers_prizes(rows, lottery)))
        return results

    main_row = next((row for row in rows if row[0] == "本数字"), None)
    if main_row is None:
        raise ValueError("CSV is missing the 本数字 row")
    try:
        bonus_index = main_row.index("ボーナス数字")
    except ValueError as error:
        raise ValueError("CSV is missing ボーナス数字") from error
    numbers = [_parse_digit(value) for value in main_row[1:bonus_index]]
    bonus = [_parse_digit(value) for value in main_row[bonus_index + 1 :]]
    lottery = LOTTERIES_BY_FAMILY[family][0]
    draw = Draw(round=round_number, draw_date=draw_date, numbers=numbers, bonus=bonus)
    validate_draw(lottery, draw)
    return [ParsedDraw(lottery, draw, _parse_loto_prizes(rows))]


def parse_bundle(payload: dict) -> list[ParsedDraw]:
    """ブラウザー収集JSONのCSV群を検査し、重複を除いて返す。"""
    if payload.get("source") != "Mizuho Bank official per-draw CSVs":
        raise ValueError("Unexpected data source")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("No CSV files found in bundle")

    parsed = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Invalid CSV file entry in bundle")  # noqa: TRY004 - JSON内容の検証エラー
        family = item.get("family")
        text = item.get("text")
        if not isinstance(family, str) or not isinstance(text, str):
            raise ValueError(  # noqa: TRY004 - JSON内容の検証エラー
                "CSV file entry must contain family and text"
            )
        parsed.extend(parse_mizuho_csv(family, text))
    return deduplicate_records(parsed)


def deduplicate_records(records: list[ParsedDraw]) -> list[ParsedDraw]:
    """複数CSV・バンドル間の同一回を統合し、内容違いは拒否する。"""
    unique: dict[tuple[LotteryType, int], ParsedDraw] = {}
    for record in records:
        key = (record.lottery, record.draw.round)
        previous = unique.get(key)
        if previous is not None and previous != record:
            raise ValueError(
                f"Conflicting duplicate data for {record.lottery.value} round {record.draw.round}"
            )
        unique[key] = record
    return sorted(unique.values(), key=lambda record: (record.lottery.value, record.draw.round))


def compare_database(db_path: Path, records: list[ParsedDraw]) -> tuple[Counter, list[str]]:
    """解析結果をDBと比較し、追加件数と内容の矛盾を返す。"""
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    summary = Counter()
    conflicts = []
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"draws", "prizes"}.issubset(tables):
            raise ValueError(f"Database is missing required tables: {db_path}")

        for record in records:
            lottery = record.lottery.value
            draw = record.draw
            existing = connection.execute(
                "SELECT draw_date, numbers, bonus FROM draws WHERE lottery = ? AND round = ?",
                (lottery, draw.round),
            ).fetchone()
            expected = (
                draw.draw_date.isoformat(),
                encode_numbers(draw.numbers),
                encode_numbers(draw.bonus),
            )
            if existing is None:
                summary["new_draws"] += 1
            elif tuple(existing) == expected:
                summary["existing_draws"] += 1
            else:
                conflicts.append(
                    f"{lottery} round {draw.round}: draw data differs from the official CSV"
                )

            for tier, amount in record.prizes.items():
                existing_prize = connection.execute(
                    "SELECT amount FROM prizes WHERE lottery = ? AND round = ? AND tier = ?",
                    (lottery, draw.round, tier),
                ).fetchone()
                if existing_prize is None:
                    summary["new_prizes"] += 1
                elif existing_prize[0] == amount:
                    summary["existing_prizes"] += 1
                else:
                    conflicts.append(
                        f"{lottery} round {draw.round} tier {tier}: "
                        f"existing amount {existing_prize[0]} differs from official amount {amount}"
                    )
    return summary, conflicts


def apply_records(db_path: Path, records: list[ParsedDraw]) -> Path:
    """オンラインバックアップ後、検査済み結果を1トランザクションで追加する。"""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}.backup-{stamp}{db_path.suffix}")
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)

    with sqlite3.connect(db_path) as connection, connection:
        connection.executemany(
            "INSERT OR IGNORE INTO draws (lottery, round, draw_date, numbers, bonus) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    record.lottery.value,
                    record.draw.round,
                    record.draw.draw_date.isoformat(),
                    encode_numbers(record.draw.numbers),
                    encode_numbers(record.draw.bonus),
                )
                for record in records
            ],
        )
        connection.executemany(
            "INSERT OR IGNORE INTO prizes (lottery, round, tier, amount) VALUES (?, ?, ?, ?)",
            [
                (record.lottery.value, record.draw.round, tier, amount)
                for record in records
                for tier, amount in record.prizes.items()
            ],
        )
    return backup_path


def _parse_japanese_date(value: str) -> dt.date:
    match = re.fullmatch(r"(令和|平成|昭和)(\d+)年(\d+)月(\d+)日", value)
    if not match:
        raise ValueError(f"Unsupported Mizuho date: {value}")
    era, year, month, day = match.groups()
    return dt.date(ERA_BASES[era] + int(year), int(month), int(day))


def _parse_digit(value: str) -> int:
    normalized = unicodedata.normalize("NFKC", value)
    if not normalized.isdigit():
        raise ValueError(f"Invalid lottery number: {value}")
    return int(normalized)


def _parse_amount(row: list[str]) -> int | None:
    for value in reversed(row[1:]):
        normalized = unicodedata.normalize("NFKC", value).replace(",", "")
        match = re.fullmatch(r"(\d+)円", normalized)
        if match:
            return int(match.group(1))
    return None


def _parse_numbers_prizes(rows: list[list[str]], lottery: LotteryType) -> dict[str, int]:
    marker = (
        "ナンバーズ３抽せん数字"
        if lottery == LotteryType.NUMBERS3
        else "ナンバーズ４抽せん数字"
    )
    start = next((index for index, row in enumerate(rows) if row[0] == marker), None)
    if start is None:
        raise ValueError(f"{marker} is missing")
    next_section = next(
        (
            index
            for index in range(start + 1, len(rows))
            if rows[index][0] in {"ナンバーズ３抽せん数字", "ナンバーズ４抽せん数字"}
        ),
        len(rows),
    )
    result = {}
    for row in rows[start + 1 : next_section]:
        label = unicodedata.normalize("NFKC", row[0])
        tier = NUMBERS_PRIZE_NAMES.get(label)
        if tier is None or (tier == "ミニ" and lottery != LotteryType.NUMBERS3):
            continue
        amount = _parse_amount(row)
        if amount is not None:
            result[tier] = amount
    return result


def _parse_loto_prizes(rows: list[list[str]]) -> dict[str, int]:
    result = {}
    for row in rows:
        label = unicodedata.normalize("NFKC", row[0])
        if not re.fullmatch(r"[1-6]等", label):
            continue
        amount = _parse_amount(row)
        if amount is not None:
            result[label] = amount
    return result
