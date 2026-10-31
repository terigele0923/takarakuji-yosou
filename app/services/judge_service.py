from app.schemas.lottery import LOTO_TIERS, Draw, LotteryType, PlayType


def judge(lottery: LotteryType, play_type: PlayType, numbers: list[int], draw: Draw) -> str | None:
    """購入した番号と抽選結果を照らし合わせ、当たった等級名を返す（外れは None）"""
    if play_type == PlayType.NORMAL:
        return _judge_loto(lottery, numbers, draw)

    straight = numbers == draw.numbers
    box = sorted(numbers) == sorted(draw.numbers)
    if play_type == PlayType.STRAIGHT:
        return "ストレート" if straight else None
    if play_type == PlayType.BOX:
        return "ボックス" if box else None
    if play_type == PlayType.SET:
        if straight:
            return "セット・ストレート"
        return "セット・ボックス" if box else None
    if play_type == PlayType.MINI:
        # ミニは購入した2桁と、抽選数字の下2桁を比べる
        return "ミニ" if numbers == draw.numbers[-2:] else None
    return None


def _judge_loto(lottery: LotteryType, numbers: list[int], draw: Draw) -> str | None:
    """ロト系の等級を、本数字の一致数とボーナス数字の一致で決める"""
    matches = len(set(numbers) & set(draw.numbers))
    bonus_hit = bool(set(numbers) & set(draw.bonus))
    for tier in LOTO_TIERS[lottery]:
        if tier.matches == matches and (tier.bonus is None or tier.bonus == bonus_hit):
            return tier.name
    return None
