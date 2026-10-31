import datetime

import pytest

from app.schemas.lottery import Draw, LotteryType, PlayType
from app.services.judge_service import judge


def draw(numbers, bonus=None):
    return Draw(round=1, draw_date=datetime.date(2026, 1, 5), numbers=numbers, bonus=bonus or [])


LOTO6 = draw([1, 5, 12, 19, 30, 41], [22])
LOTO7 = draw([1, 2, 3, 4, 5, 6, 7], [10, 20])
MINILOTO = draw([1, 8, 15, 22, 31], [4])


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [
        ([1, 5, 12, 19, 30, 41], "1等"),
        ([1, 5, 12, 19, 30, 22], "2等"),
        ([1, 5, 12, 19, 30, 40], "3等"),
        ([1, 5, 12, 19, 2, 3], "4等"),
        ([1, 5, 12, 22, 2, 3], "5等"),   # ボーナス数字は 5等の条件に関係しない
        ([1, 5, 2, 3, 4, 22], None),
        ([2, 3, 4, 6, 7, 8], None),
    ],
)
def test_ロト6の等級(numbers, expected):
    assert judge(LotteryType.LOTO6, PlayType.NORMAL, numbers, LOTO6) == expected


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [
        ([1, 2, 3, 4, 5, 6, 7], "1等"),
        ([1, 2, 3, 4, 5, 6, 20], "2等"),
        ([1, 2, 3, 4, 5, 6, 30], "3等"),
        ([1, 2, 3, 4, 5, 30, 31], "4等"),
        ([1, 2, 3, 4, 30, 31, 32], "5等"),
        ([1, 2, 3, 10, 30, 31, 32], "6等"),
        ([1, 2, 3, 30, 31, 32, 33], None),   # 6等はボーナス数字の一致が必要
    ],
)
def test_ロト7の等級(numbers, expected):
    assert judge(LotteryType.LOTO7, PlayType.NORMAL, numbers, LOTO7) == expected


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [
        ([1, 8, 15, 22, 31], "1等"),
        ([1, 8, 15, 22, 4], "2等"),
        ([1, 8, 15, 22, 30], "3等"),
        ([1, 8, 15, 2, 3], "4等"),
        ([1, 8, 2, 3, 4], None),
    ],
)
def test_ミニロトの等級(numbers, expected):
    assert judge(LotteryType.MINILOTO, PlayType.NORMAL, numbers, MINILOTO) == expected


@pytest.mark.parametrize(
    ("play_type", "numbers", "expected"),
    [
        (PlayType.STRAIGHT, [4, 3, 6, 1], "ストレート"),
        (PlayType.STRAIGHT, [1, 3, 6, 4], None),
        (PlayType.BOX, [1, 3, 6, 4], "ボックス"),
        (PlayType.BOX, [4, 3, 6, 1], "ボックス"),
        (PlayType.BOX, [4, 3, 6, 2], None),
        (PlayType.SET, [4, 3, 6, 1], "セット・ストレート"),
        (PlayType.SET, [1, 3, 6, 4], "セット・ボックス"),
        (PlayType.SET, [1, 3, 6, 5], None),
    ],
)
def test_ナンバーズ4の申込タイプごとの当たり(play_type, numbers, expected):
    assert judge(LotteryType.NUMBERS4, play_type, numbers, draw([4, 3, 6, 1])) == expected


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [([8, 4], "ミニ"), ([4, 8], None), ([0, 8], None)],
)
def test_ナンバーズ3のミニは下2桁の並び順で当たる(numbers, expected):
    assert judge(LotteryType.NUMBERS3, PlayType.MINI, numbers, draw([0, 8, 4])) == expected
