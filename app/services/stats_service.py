import datetime
from collections.abc import Callable

from app.config import STATS_YEARS
from app.schemas.lottery import RULES, Draw, LotteryType
from app.schemas.stats import LotteryStats, NumberStat


def calculate_stats(lottery: LotteryType, draws: list[Draw], years: int = STATS_YEARS) -> LotteryStats:
    """直近の指定年数分の抽選結果から、番号ごとの出た回数と最後に出てからの回数を数える"""
    rule = RULES[lottery]
    targets = _recent(sorted(draws, key=lambda draw: draw.round), years)
    candidates = range(rule.min, rule.max + 1)

    if rule.by_position:
        # ナンバーズは桁ごとに数える
        positions = [
            _count(targets, lambda draw, index=index: [draw.numbers[index]], candidates)
            for index in range(rule.count)
        ]
    else:
        # ロト系は本数字全体で数える（ボーナス数字は含めない）
        positions = [_count(targets, lambda draw: draw.numbers, candidates)]

    return LotteryStats(
        lottery=lottery,
        total_draws=len(targets),
        first_date=targets[0].draw_date if targets else None,
        last_date=targets[-1].draw_date if targets else None,
        last_round=targets[-1].round if targets else None,
        positions=positions,
    )


def _recent(draws: list[Draw], years: int) -> list[Draw]:
    """最新の抽選日から指定年数以内の抽選結果だけを返す"""
    if not draws:
        return []
    cutoff = _years_before(draws[-1].draw_date, years)
    return [draw for draw in draws if draw.draw_date > cutoff]


def _years_before(day: datetime.date, years: int) -> datetime.date:
    """指定した日の、指定年数前の日を返す（2月29日は2月28日にする）"""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def _count(
    draws: list[Draw],
    values_of: Callable[[Draw], list[int]],
    candidates: range,
) -> list[NumberStat]:
    """候補の番号ごとに、出た回数と最後に出てから何回たったかを数える"""
    counts = {number: 0 for number in candidates}
    last_index: dict[int, int] = {}
    for index, draw in enumerate(draws):
        for value in values_of(draw):
            counts[value] += 1
            last_index[value] = index

    latest = len(draws) - 1
    return [
        NumberStat(
            number=number,
            count=counts[number],
            gap=latest - last_index[number] if number in last_index else None,
        )
        for number in candidates
    ]
