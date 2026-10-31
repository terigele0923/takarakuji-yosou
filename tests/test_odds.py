import pytest

from app.schemas.lottery import LotteryType, PlayType
from app.services.odds_service import available_play_types, calculate_odds


def odds_by_tier(lottery, numbers):
    return {odds.tier: odds for odds in calculate_odds(lottery, numbers)}


def test_ロト6の等級ごとの当せん確率():
    odds = odds_by_tier(LotteryType.LOTO6, [1, 2, 3, 4, 5, 6])
    assert list(odds) == ["1等", "2等", "3等", "4等", "5等"]
    assert odds["1等"].odds_text == "1/6,096,454"
    assert odds["2等"].odds_text == "約1/1,016,076"
    assert odds["3等"].odds_text == "約1/28,224"
    assert odds["4等"].odds_text == "約1/610"
    assert odds["5等"].odds_text == "約1/39"
    assert odds["1等"].probability == pytest.approx(1 / 6_096_454)
    assert all(item.play_type == PlayType.NORMAL for item in odds.values())


def test_ロト7の等級ごとの当せん確率():
    odds = odds_by_tier(LotteryType.LOTO7, [1, 2, 3, 4, 5, 6, 7])
    assert list(odds) == ["1等", "2等", "3等", "4等", "5等", "6等"]
    assert odds["1等"].odds_text == "1/10,295,472"
    assert odds["2等"].odds_text == "約1/735,391"
    assert odds["3等"].odds_text == "約1/52,528"


def test_ミニロトの等級ごとの当せん確率():
    odds = odds_by_tier(LotteryType.MINILOTO, [1, 2, 3, 4, 5])
    assert list(odds) == ["1等", "2等", "3等", "4等"]
    assert odds["1等"].odds_text == "1/169,911"
    assert odds["2等"].odds_text == "約1/33,982"


@pytest.mark.parametrize("lottery", [LotteryType.MINILOTO, LotteryType.LOTO6, LotteryType.LOTO7])
def test_ロト系はどの番号でも同じ確率で合計は1未満(lottery):
    count = {LotteryType.MINILOTO: 5, LotteryType.LOTO6: 6, LotteryType.LOTO7: 7}[lottery]
    first = calculate_odds(lottery, list(range(1, count + 1)))
    second = calculate_odds(lottery, list(range(10, 10 + count)))
    assert first == second
    assert 0 < sum(item.probability for item in first) < 1


def test_ナンバーズ4のボックスは数字の並べ方の数で決まる():
    odds = odds_by_tier(LotteryType.NUMBERS4, [4, 3, 6, 1])
    assert odds["ストレート"].odds_text == "1/10,000"
    assert odds["ボックス"].probability == pytest.approx(24 / 10_000)
    assert odds["セット・ストレート"].odds_text == "1/10,000"
    assert odds["セット・ボックス"].probability == pytest.approx(23 / 10_000)
    assert "ミニ" not in odds


def test_ナンバーズ3は同じ数字が2つあるとボックスが3通り():
    odds = odds_by_tier(LotteryType.NUMBERS3, [0, 8, 8])
    assert odds["ストレート"].odds_text == "1/1,000"
    assert odds["ボックス"].probability == pytest.approx(3 / 1_000)
    assert odds["セット・ボックス"].probability == pytest.approx(2 / 1_000)
    assert odds["ミニ"].odds_text == "1/100"


def test_ゾロ目はボックスとセットを選べない():
    assert available_play_types(LotteryType.NUMBERS3, [7, 7, 7]) == [PlayType.STRAIGHT, PlayType.MINI]
    assert available_play_types(LotteryType.NUMBERS4, [1, 1, 1, 1]) == [PlayType.STRAIGHT]
    tiers = odds_by_tier(LotteryType.NUMBERS3, [7, 7, 7])
    assert list(tiers) == ["ストレート", "ミニ"]


def test_選べる申込タイプ():
    assert available_play_types(LotteryType.NUMBERS3, [1, 2, 3]) == [
        PlayType.STRAIGHT, PlayType.BOX, PlayType.SET, PlayType.MINI,
    ]
    assert available_play_types(LotteryType.NUMBERS4, [1, 2, 3, 4]) == [
        PlayType.STRAIGHT, PlayType.BOX, PlayType.SET,
    ]
    assert available_play_types(LotteryType.LOTO6, [1, 2, 3, 4, 5, 6]) == [PlayType.NORMAL]
