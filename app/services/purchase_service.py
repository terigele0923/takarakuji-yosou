import datetime
from contextlib import closing
from pathlib import Path

from app.config import DB_PATH
from app.db import connect
from app.schemas.lottery import RULES, LotteryType, PlayType
from app.schemas.purchase import (
    PurchaseListResponse,
    PurchaseRecord,
    PurchaseRequest,
    PurchaseResponse,
    PurchaseStatus,
    PurchaseSummary,
)
from app.services.judge_service import judge
from app.services.lottery_data import (
    load_average_prizes,
    load_draw,
    load_prize,
    validate_numbers,
)
from app.services.odds_service import available_play_types, calculate_odds


def save_purchase(request: PurchaseRequest, db_path: Path = DB_PATH) -> PurchaseResponse:
    """購入した番号を、ルールと申込タイプを確かめて DB に記録する"""
    rule = RULES[request.lottery]
    validate_numbers(request.lottery, request.numbers)
    if request.play_type not in available_play_types(request.lottery, request.numbers):
        raise ValueError(f"{rule.name}のこの番号では、その申込タイプは選べません")

    if request.play_type == PlayType.MINI:
        # ミニは下2桁を買う
        numbers = request.numbers[-2:]
    elif rule.by_position:
        numbers = request.numbers
    else:
        numbers = sorted(request.numbers)
    purchased_at = datetime.datetime.now().replace(microsecond=0)

    with closing(connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO purchases (lottery, round, numbers, play_type, price, purchased_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                request.lottery.value,
                request.round,
                ",".join(str(number) for number in numbers),
                request.play_type.value,
                rule.price,
                purchased_at.isoformat(),
            ),
        )
        purchase_id = cursor.lastrowid

    return PurchaseResponse(
        id=purchase_id,
        lottery=request.lottery,
        round=request.round,
        numbers=numbers,
        play_type=request.play_type,
        price=rule.price,
        purchased_at=purchased_at,
    )


def check_results(db_path: Path = DB_PATH) -> PurchaseListResponse:
    """結果がまだの購入を、抽選結果と照らし合わせて等級と賞金を記録し、一覧を返す"""
    with closing(connect(db_path)) as conn:
        rows = conn.execute("SELECT * FROM purchases WHERE prize IS NULL").fetchall()

    updates = []
    for row in rows:
        lottery = LotteryType(row["lottery"])
        draw = load_draw(lottery, row["round"], db_path)
        if draw is None:
            continue
        tier = judge(lottery, PlayType(row["play_type"]), _split(row["numbers"]), draw)
        if tier is None:
            updates.append((None, 0, row["id"]))
        else:
            # 賞金がまだ DB になければ、等級だけ記録して金額は空のままにする
            updates.append((tier, load_prize(lottery, row["round"], tier, db_path), row["id"]))

    with closing(connect(db_path)) as conn, conn:
        conn.executemany("UPDATE purchases SET tier = ?, prize = ? WHERE id = ?", updates)
    return list_purchases(db_path)


def list_purchases(db_path: Path = DB_PATH) -> PurchaseListResponse:
    """購入の一覧（新しい順）と、全体の収支を返す"""
    with closing(connect(db_path)) as conn:
        rows = conn.execute("SELECT * FROM purchases ORDER BY id DESC").fetchall()

    averages: dict[LotteryType, dict[str, float]] = {}
    records = []
    for row in rows:
        lottery = LotteryType(row["lottery"])
        if lottery not in averages:
            averages[lottery] = load_average_prizes(lottery, db_path)
        records.append(_to_record(row, averages[lottery]))

    return PurchaseListResponse(purchases=records, summary=_summarize(records))


def expected_return(
    lottery: LotteryType,
    play_type: PlayType,
    numbers: list[int],
    average_prizes: dict[str, float],
) -> float | None:
    """1口の期待される戻り（等級ごとの当せん確率 × 平均の賞金の合計）を返す（賞金のデータが足りなければ None）"""
    total = 0.0
    for odds in calculate_odds(lottery, numbers):
        if odds.play_type != play_type:
            continue
        if odds.tier not in average_prizes:
            return None
        total += odds.probability * average_prizes[odds.tier]
    return total


def _to_record(row, average_prizes: dict[str, float]) -> PurchaseRecord:
    """DB の1行を、結果と期待される戻りを付けた購入1件分にする"""
    lottery = LotteryType(row["lottery"])
    play_type = PlayType(row["play_type"])
    numbers = _split(row["numbers"])
    return PurchaseRecord(
        id=row["id"],
        lottery=lottery,
        name=RULES[lottery].name,
        round=row["round"],
        numbers=numbers,
        play_type=play_type,
        price=row["price"],
        purchased_at=row["purchased_at"],
        status=_status(row["tier"], row["prize"]),
        tier=row["tier"],
        prize=row["prize"],
        expected_return=expected_return(lottery, play_type, numbers, average_prizes),
    )


def _status(tier: str | None, prize: int | None) -> PurchaseStatus:
    """等級と賞金の記録から、結果の状態を決める"""
    if prize is None:
        return PurchaseStatus.PENDING if tier is None else PurchaseStatus.PRIZE_UNKNOWN
    return PurchaseStatus.WON if prize > 0 else PurchaseStatus.LOST


def _summarize(records: list[PurchaseRecord]) -> PurchaseSummary:
    """購入の一覧から、全体の収支をまとめる"""
    spent = sum(record.price for record in records)
    won = sum(record.prize or 0 for record in records)
    return PurchaseSummary(
        count=len(records),
        spent=spent,
        won=won,
        profit=won - spent,
        pending_count=sum(
            record.status in (PurchaseStatus.PENDING, PurchaseStatus.PRIZE_UNKNOWN)
            for record in records
        ),
        expected_return=sum(record.expected_return or 0 for record in records),
        expected_is_partial=any(record.expected_return is None for record in records),
    )


def _split(text: str) -> list[int]:
    """カンマ区切りの文字列を番号の一覧にする"""
    return [int(value) for value in text.split(",")] if text else []
