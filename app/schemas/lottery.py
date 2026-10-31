import datetime
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


class LotteryType(str, Enum):
    """宝くじの種類（値は DB の lottery 列に使う）"""

    NUMBERS3 = "numbers3"
    NUMBERS4 = "numbers4"
    MINILOTO = "miniloto"
    LOTO6 = "loto6"
    LOTO7 = "loto7"


class PlayType(str, Enum):
    """申込タイプ（買い方）"""

    NORMAL = "normal"      # ロト系
    STRAIGHT = "straight"  # 数字と並び順が一致
    BOX = "box"            # 並び順は問わず数字が一致（ゾロ目は買えない）
    SET = "set"            # ストレートとボックスを半分ずつ（ゾロ目は買えない）
    MINI = "mini"          # 下2桁の数字と並び順が一致（ナンバーズ3のみ）


@dataclass(frozen=True)
class LotteryRule:
    """宝くじの種類ごとの番号のルール"""

    name: str                           # 表示名
    count: int                          # 本数字の数（ナンバーズは桁数）
    min: int                            # 番号の最小値
    max: int                            # 番号の最大値
    bonus_count: int                    # ボーナス数字の数
    allow_duplicates: bool              # 同じ番号が出てよいか（ナンバーズは桁ごとなので重複あり）
    price: int                          # 1口の金額（円）
    play_types: tuple[PlayType, ...]    # 選べる申込タイプ

    @property
    def by_position(self) -> bool:
        """桁ごとに数字を扱う種類か（ナンバーズ）"""
        return self.allow_duplicates


RULES: dict[LotteryType, LotteryRule] = {
    LotteryType.NUMBERS3: LotteryRule(
        "ナンバーズ3", 3, 0, 9, 0, True, 200,
        (PlayType.STRAIGHT, PlayType.BOX, PlayType.SET, PlayType.MINI),
    ),
    LotteryType.NUMBERS4: LotteryRule(
        "ナンバーズ4", 4, 0, 9, 0, True, 200,
        (PlayType.STRAIGHT, PlayType.BOX, PlayType.SET),
    ),
    LotteryType.MINILOTO: LotteryRule("ミニロト", 5, 1, 31, 1, False, 200, (PlayType.NORMAL,)),
    LotteryType.LOTO6: LotteryRule("ロト6", 6, 1, 43, 1, False, 200, (PlayType.NORMAL,)),
    LotteryType.LOTO7: LotteryRule("ロト7", 7, 1, 37, 2, False, 300, (PlayType.NORMAL,)),
}


@dataclass(frozen=True)
class LotoTier:
    """ロト系の等級の条件"""

    name: str            # 等級名
    matches: int         # 本数字と一致する数
    bonus: bool | None   # True：ボーナス数字の一致が必要、False：一致しないこと、None：問わない


LOTO_TIERS: dict[LotteryType, tuple[LotoTier, ...]] = {
    LotteryType.MINILOTO: (
        LotoTier("1等", 5, None),
        LotoTier("2等", 4, True),
        LotoTier("3等", 4, False),
        LotoTier("4等", 3, None),
    ),
    LotteryType.LOTO6: (
        LotoTier("1等", 6, None),
        LotoTier("2等", 5, True),
        LotoTier("3等", 5, False),
        LotoTier("4等", 4, None),
        LotoTier("5等", 3, None),
    ),
    LotteryType.LOTO7: (
        LotoTier("1等", 7, None),
        LotoTier("2等", 6, True),
        LotoTier("3等", 6, False),
        LotoTier("4等", 5, None),
        LotoTier("5等", 4, None),
        LotoTier("6等", 3, True),
    ),
}


class Draw(BaseModel):
    """1回分の抽選結果"""

    round: int                  # 回
    draw_date: datetime.date    # 抽選日
    numbers: list[int]          # 本数字（ナンバーズは桁の順）
    bonus: list[int]            # ボーナス数字（ナンバーズは空）


class LotteryUpdateResponse(BaseModel):
    added_draws: int
    added_prizes: int
