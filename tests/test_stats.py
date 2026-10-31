import datetime

from app.schemas.lottery import Draw, LotteryType
from app.services.stats_service import calculate_stats


def make_draw(round, numbers, bonus=None, draw_date=None):
    return Draw(
        round=round,
        draw_date=draw_date or datetime.date(2026, 1, 1) + datetime.timedelta(days=round),
        numbers=numbers,
        bonus=bonus or [],
    )


def stat_of(stats, number, position=0):
    return next(stat for stat in stats.positions[position] if stat.number == number)


def test_ロト6は番号ごとに出た回数と最後に出てからの回数を数える():
    draws = [
        make_draw(1, [1, 2, 3, 4, 5, 6], [7]),
        make_draw(2, [1, 2, 3, 10, 11, 12], [13]),
        make_draw(3, [1, 20, 21, 22, 23, 43], [7]),
    ]
    stats = calculate_stats(LotteryType.LOTO6, draws)

    assert stats.total_draws == 3
    assert stats.last_round == 3
    assert len(stats.positions) == 1
    assert [stat.number for stat in stats.positions[0]] == list(range(1, 44))
    assert stat_of(stats, 1).count == 3 and stat_of(stats, 1).gap == 0
    assert stat_of(stats, 2).count == 2 and stat_of(stats, 2).gap == 1
    assert stat_of(stats, 4).count == 1 and stat_of(stats, 4).gap == 2
    assert stat_of(stats, 43).count == 1 and stat_of(stats, 43).gap == 0


def test_ボーナス数字は数えない():
    stats = calculate_stats(LotteryType.LOTO6, [make_draw(1, [1, 2, 3, 4, 5, 6], [7])])
    assert stat_of(stats, 7).count == 0
    assert stat_of(stats, 7).gap is None


def test_ナンバーズ3は桁ごとに数える():
    draws = [
        make_draw(1, [0, 8, 8]),
        make_draw(2, [0, 1, 9]),
    ]
    stats = calculate_stats(LotteryType.NUMBERS3, draws)

    assert len(stats.positions) == 3
    assert [stat.number for stat in stats.positions[0]] == list(range(0, 10))
    assert stat_of(stats, 0, position=0).count == 2
    assert stat_of(stats, 0, position=0).gap == 0
    assert stat_of(stats, 8, position=1).count == 1
    assert stat_of(stats, 8, position=1).gap == 1
    assert stat_of(stats, 8, position=2).count == 1
    assert stat_of(stats, 0, position=2).count == 0


def test_回の順に並べてから数える():
    draws = [
        make_draw(2, [1, 2, 3, 4, 5]),
        make_draw(1, [6, 7, 8, 9, 10]),
    ]
    stats = calculate_stats(LotteryType.MINILOTO, draws)
    assert stats.last_round == 2
    assert stat_of(stats, 6).gap == 1
    assert stat_of(stats, 1).gap == 0


def test_最新の抽選日から指定年数より前の回は数えない():
    draws = [
        make_draw(1, [1, 2, 3, 4, 5, 6, 7], [8, 9], datetime.date(2016, 1, 5)),
        make_draw(2, [1, 2, 3, 4, 5, 6, 7], [8, 9], datetime.date(2016, 1, 6)),
        make_draw(3, [10, 11, 12, 13, 14, 15, 16], [8, 9], datetime.date(2026, 1, 5)),
    ]
    stats = calculate_stats(LotteryType.LOTO7, draws, years=10)

    assert stats.total_draws == 2
    assert stats.first_date == datetime.date(2016, 1, 6)
    assert stats.last_date == datetime.date(2026, 1, 5)
    assert stat_of(stats, 1).count == 1


def test_最新の抽選日が2月29日でも期間を計算できる():
    draws = [
        make_draw(1, [1, 2, 3, 4, 5, 6], [7], datetime.date(2014, 2, 28)),
        make_draw(2, [1, 2, 3, 4, 5, 6], [7], datetime.date(2024, 2, 29)),
    ]
    stats = calculate_stats(LotteryType.LOTO6, draws, years=10)
    assert stats.total_draws == 1


def test_データがなければ0回として返す():
    stats = calculate_stats(LotteryType.LOTO6, [])
    assert stats.total_draws == 0
    assert stats.last_round is None
    assert all(stat.count == 0 and stat.gap is None for stat in stats.positions[0])
