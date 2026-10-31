from collections import Counter
from fractions import Fraction
from math import comb, factorial, prod

from app.schemas.lottery import LOTO_TIERS, RULES, LotoTier, LotteryType, PlayType
from app.schemas.odds import TierOdds


def calculate_odds(lottery: LotteryType, numbers: list[int]) -> list[TierOdds]:
    """番号1組の、申込タイプ・等級ごとの当せん確率を返す"""
    if RULES[lottery].by_position:
        return _numbers_odds(lottery, numbers)
    return [
        _to_odds(PlayType.NORMAL, tier.name, _loto_probability(lottery, tier))
        for tier in LOTO_TIERS[lottery]
    ]


def available_play_types(lottery: LotteryType, numbers: list[int]) -> list[PlayType]:
    """番号1組で選べる申込タイプを返す（ゾロ目はボックスとセットを選べない）"""
    rule = RULES[lottery]
    if rule.by_position and len(set(numbers)) == 1:
        return [play for play in rule.play_types if play not in (PlayType.BOX, PlayType.SET)]
    return list(rule.play_types)


def _loto_probability(lottery: LotteryType, tier: LotoTier) -> Fraction:
    """ロト系の1つの等級の当せん確率を、組み合わせの数から計算する"""
    rule = RULES[lottery]
    total = rule.max - rule.min + 1
    picks = rule.count
    # 本数字とちょうど tier.matches 個一致する確率
    main = Fraction(
        comb(picks, tier.matches) * comb(total - picks, picks - tier.matches),
        comb(total, picks),
    )
    if tier.bonus is None:
        return main

    # 本数字に入らなかった番号から、ボーナス数字が選ばれる
    rest = total - picks
    missed = picks - tier.matches
    no_bonus = Fraction(comb(rest - missed, rule.bonus_count), comb(rest, rule.bonus_count))
    return main * (1 - no_bonus if tier.bonus else no_bonus)


def _numbers_odds(lottery: LotteryType, numbers: list[int]) -> list[TierOdds]:
    """ナンバーズの申込タイプごとの当せん確率を計算する"""
    total = 10 ** len(numbers)
    # 数字の並べ方の数（例：4361 は 24 通り、088 は 3 通り）
    arrangements = factorial(len(numbers)) // prod(
        factorial(count) for count in Counter(numbers).values()
    )

    odds = []
    for play in available_play_types(lottery, numbers):
        if play == PlayType.STRAIGHT:
            odds.append(_to_odds(play, "ストレート", Fraction(1, total)))
        elif play == PlayType.BOX:
            odds.append(_to_odds(play, "ボックス", Fraction(arrangements, total)))
        elif play == PlayType.SET:
            odds.append(_to_odds(play, "セット・ストレート", Fraction(1, total)))
            odds.append(_to_odds(play, "セット・ボックス", Fraction(arrangements - 1, total)))
        elif play == PlayType.MINI:
            odds.append(_to_odds(play, "ミニ", Fraction(1, 100)))
    return odds


def _to_odds(play_type: PlayType, tier: str, probability: Fraction) -> TierOdds:
    """確率を、表示用の文字（1/○○）と合わせて返す"""
    one_in = 1 / probability
    if one_in.denominator == 1:
        text = f"1/{one_in.numerator:,}"
    else:
        text = f"約1/{round(one_in):,}"
    return TierOdds(
        play_type=play_type,
        tier=tier,
        probability=float(probability),
        odds_text=text,
    )
