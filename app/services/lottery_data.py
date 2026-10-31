from contextlib import closing
from pathlib import Path

from app.config import DB_PATH
from app.db import connect
from app.schemas.lottery import RULES, Draw, LotteryType


def load_draws(lottery: LotteryType, db_path: Path = DB_PATH) -> list[Draw]:
    """過去の抽選結果を DB から読み込み、回の順に並べて返す"""
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT round, draw_date, numbers, bonus FROM draws WHERE lottery = ? ORDER BY round",
            (lottery.value,),
        ).fetchall()
    return [_to_draw(row) for row in rows]


def load_draw(lottery: LotteryType, round: int, db_path: Path = DB_PATH) -> Draw | None:
    """指定した回の抽選結果を返す（まだなければ None）"""
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT round, draw_date, numbers, bonus FROM draws WHERE lottery = ? AND round = ?",
            (lottery.value, round),
        ).fetchone()
    return _to_draw(row) if row else None


def save_prizes(
    lottery: LotteryType,
    prizes: dict[int, dict[str, int]],
    db_path: Path = DB_PATH,
) -> int:
    """回ごと・等級ごとの賞金（{回: {等級: 金額}}）を保存し、新しく保存した件数を返す（保存済みは飛ばす）"""
    with closing(connect(db_path)) as conn, conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO prizes (lottery, round, tier, amount) VALUES (?, ?, ?, ?)",
            [
                (lottery.value, round, tier, amount)
                for round, amounts in prizes.items()
                for tier, amount in amounts.items()
            ],
        )
        return conn.total_changes - before


def load_prize(lottery: LotteryType, round: int, tier: str, db_path: Path = DB_PATH) -> int | None:
    """指定した回・等級の1口あたりの賞金を返す（まだなければ None）"""
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT amount FROM prizes WHERE lottery = ? AND round = ? AND tier = ?",
            (lottery.value, round, tier),
        ).fetchone()
    return row["amount"] if row else None


def load_average_prizes(lottery: LotteryType, db_path: Path = DB_PATH) -> dict[str, float]:
    """等級ごとの、これまでの賞金の平均を返す（{等級: 平均金額}）"""
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT tier, AVG(amount) AS average FROM prizes WHERE lottery = ? GROUP BY tier",
            (lottery.value,),
        ).fetchall()
    return {row["tier"]: row["average"] for row in rows}


def _to_draw(row) -> Draw:
    """DB の1行を抽選結果に変換する"""
    return Draw(
        round=row["round"],
        draw_date=row["draw_date"],
        numbers=_split(row["numbers"]),
        bonus=_split(row["bonus"]),
    )


def save_draws(lottery: LotteryType, draws: list[Draw], db_path: Path = DB_PATH) -> int:
    """抽選結果をルールで確かめて DB に保存し、新しく保存した件数を返す（保存済みの回は飛ばす）"""
    for draw in draws:
        try:
            validate_draw(lottery, draw)
        except ValueError as error:
            raise ValueError(f"第{draw.round}回: {error}") from error

    # 保存が終わったら確定し、途中で失敗したら取り消す
    with closing(connect(db_path)) as conn, conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO draws (lottery, round, draw_date, numbers, bonus)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (
                    lottery.value,
                    draw.round,
                    draw.draw_date.isoformat(),
                    _join(draw.numbers),
                    _join(draw.bonus),
                )
                for draw in draws
            ],
        )
        return conn.total_changes - before


def validate_draw(lottery: LotteryType, draw: Draw) -> None:
    """抽選結果が種類ごとのルール（数・範囲・重複）に合っているか確かめる"""
    rule = RULES[lottery]
    if len(draw.numbers) != rule.count:
        raise ValueError(f"本数字は {rule.count} 個です")
    if len(draw.bonus) != rule.bonus_count:
        raise ValueError(f"ボーナス数字は {rule.bonus_count} 個です")
    _check_values(lottery, draw.numbers + draw.bonus)


def validate_numbers(lottery: LotteryType, numbers: list[int]) -> None:
    """予想した本数字が種類ごとのルール（数・範囲・重複）に合っているか確かめる"""
    rule = RULES[lottery]
    if len(numbers) != rule.count:
        raise ValueError(f"本数字は {rule.count} 個です")
    _check_values(lottery, numbers)


def _check_values(lottery: LotteryType, values: list[int]) -> None:
    """番号が範囲内で、重複してはいけない種類なら重複がないか確かめる"""
    rule = RULES[lottery]
    if any(not rule.min <= value <= rule.max for value in values):
        raise ValueError(f"番号は {rule.min}〜{rule.max} の範囲です")
    if not rule.allow_duplicates and len(set(values)) != len(values):
        raise ValueError("同じ番号が重複しています")


def _join(values: list[int]) -> str:
    """番号の一覧をカンマ区切りの文字列にする"""
    return ",".join(str(value) for value in values)


def _split(text: str) -> list[int]:
    """カンマ区切りの文字列を番号の一覧にする（空なら空の一覧）"""
    return [int(value) for value in text.split(",")] if text else []
