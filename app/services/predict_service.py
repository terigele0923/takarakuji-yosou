from langchain_openai import ChatOpenAI

from app.config import MODEL_NAME
from app.schemas.lottery import RULES, LotteryRule, LotteryType
from app.schemas.predict import (
    AiPredictedSet,
    PredictedSet,
    PredictionOutput,
    PredictResponse,
)
from app.schemas.stats import LotteryStats, NumberStat
from app.services.lottery_data import load_draws, validate_numbers
from app.services.odds_service import calculate_odds
from app.services.stats_service import calculate_stats

# AI がルールに合わない番号を返したときに、やり直す回数の上限
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = (
    "あなたは宝くじの過去の抽選結果を集計したデータをもとに、番号を選ぶアシスタントです。"
    "抽選は毎回ランダムで、過去の結果から当せんの確率を上げることはできません。"
    "そのうえで、渡された集計結果を参考に、ルールに合う番号を指定された組数だけ選び、"
    "組ごとに選んだ理由を集計結果の数字を使って説明してください。"
)


class NoDrawDataError(Exception):
    """抽選結果のデータがまだないときのエラー"""


class InvalidPredictionError(Exception):
    """AI がルールに合う番号を返さなかったときのエラー"""


def predict(lottery: LotteryType, count: int = 1) -> PredictResponse:
    """過去の抽選結果を集計し、AI に番号を指定した組数だけ選んでもらう"""
    rule = RULES[lottery]
    draws = load_draws(lottery)
    if not draws:
        raise NoDrawDataError(f"{rule.name}の抽選結果がまだありません")

    stats = calculate_stats(lottery, draws)
    llm = ChatOpenAI(model=MODEL_NAME).with_structured_output(PredictionOutput)
    messages = [("system", SYSTEM_PROMPT), ("human", build_prompt(rule, stats, count))]

    for _ in range(MAX_ATTEMPTS):
        output = llm.invoke(messages)
        sets = _to_predicted_sets(lottery, output.sets, count)
        if sets is None:
            continue
        return PredictResponse(
            lottery=lottery,
            name=rule.name,
            price=rule.price,
            next_round=stats.last_round + 1,
            sets=sets,
            total_draws=stats.total_draws,
            first_date=stats.first_date,
            last_date=stats.last_date,
            last_round=stats.last_round,
        )

    raise InvalidPredictionError("AI がルールに合う番号を返しませんでした。もう一度お試しください")


def _to_predicted_sets(
    lottery: LotteryType,
    ai_sets: list[AiPredictedSet],
    count: int,
) -> list[PredictedSet] | None:
    """AI の答えを確かめて、確率を付けた番号の組にする（組数・ルール・重複が合わなければ None）"""
    rule = RULES[lottery]
    if len(ai_sets) != count:
        return None

    sets = []
    seen = set()
    for ai_set in ai_sets:
        try:
            validate_numbers(lottery, ai_set.numbers)
        except ValueError:
            return None
        numbers = ai_set.numbers if rule.by_position else sorted(ai_set.numbers)
        if tuple(numbers) in seen:
            return None
        seen.add(tuple(numbers))
        sets.append(PredictedSet(
            numbers=numbers,
            reason=ai_set.reason,
            odds=calculate_odds(lottery, numbers),
        ))
    return sets


def build_prompt(rule: LotteryRule, stats: LotteryStats, count: int = 1) -> str:
    """AI に渡す、ルールと集計結果の文章を作る"""
    if rule.by_position:
        how_to_pick = (
            f"各桁 {rule.min}〜{rule.max} の数字を1つずつ、{rule.count}桁を選ぶ"
            "（同じ数字を選んでもよい）。numbers には左の桁から順に入れる"
        )
    else:
        how_to_pick = f"{rule.min}〜{rule.max} から異なる番号を {rule.count} 個選ぶ"

    lines = [
        f"宝くじ：{rule.name}",
        f"選び方：{how_to_pick}",
        f"組数：{count}組（同じ組を2回選ばない）",
        f"集計期間：{stats.first_date}〜{stats.last_date}（第{stats.last_round}回まで、{stats.total_draws}回分）",
        "「最後に出てから」は、何回前の抽選で最後に出たか（0 は最新の回）。",
    ]
    for index, numbers in enumerate(stats.positions):
        if rule.by_position:
            lines.append(f"\n[左から{index + 1}桁目]")
        lines.append("番号,出た回数,最後に出てから")
        lines.extend(_format_stat(stat) for stat in numbers)
    return "\n".join(lines)


def _format_stat(stat: NumberStat) -> str:
    """番号1つの集計を、AI に渡す1行の文字にする"""
    gap = "未出" if stat.gap is None else str(stat.gap)
    return f"{stat.number},{stat.count},{gap}"
