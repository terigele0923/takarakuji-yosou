from langchain_openai import ChatOpenAI

from app.config import MODEL_NAME
from app.schemas.lottery import RULES, Draw, LotteryRule, LotteryType
from app.schemas.predict import (
    AiPredictedSet,
    CooccurrenceMatrix,
    FrequencyMatrix,
    PredictedSet,
    PredictionOutput,
    PredictResponse,
)
from app.schemas.stats import LotteryStats, NumberStat
from app.services.lottery_data import load_draws, validate_numbers
from app.services.odds_service import calculate_odds
from app.services.prompt_loader import load_analysis_prompt
from app.services.stats_service import calculate_stats
from app.services.trend_service import build_history_matrices, candidate_trend

# AI がルールに合わない番号を返したときに、やり直す回数の上限
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = (
    "あなたは宝くじの過去の抽選結果を集計したデータをもとに、番号を選ぶアシスタントです。"
    "抽選は毎回ランダムで、過去の結果から当せんの確率を上げることはできません。"
    "そのうえで、渡された集計結果を参考に、ルールに合う番号を指定された組数だけ選び、"
    "組ごとに選んだ理由を集計結果の数字を使って説明してください。"
    "過去の傾向を次回の当選確率と誤認させる表現はしないでください。"
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
    frequency_matrices, cooccurrence_matrices = build_history_matrices(lottery, draws)
    llm = ChatOpenAI(model=MODEL_NAME).with_structured_output(PredictionOutput)
    messages = [
        ("system", f"{SYSTEM_PROMPT}\n\n{load_analysis_prompt()}"),
        (
            "human",
            build_prompt(
                rule,
                stats,
                count,
                frequency_matrices,
                cooccurrence_matrices,
            ),
        ),
    ]

    for _ in range(MAX_ATTEMPTS):
        output = llm.invoke(messages)
        sets = _to_predicted_sets(lottery, output.sets, count, draws)
        if sets is None:
            continue
        metric = "桁位置つきHamming距離" if rule.by_position else "番号集合のJaccard距離"
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
            trend_metric=metric,
            trend_draw_count=len(draws),
            trend_first_date=min(draw.draw_date for draw in draws),
            trend_last_date=max(draw.draw_date for draw in draws),
            frequency_matrices=frequency_matrices,
            cooccurrence_matrices=cooccurrence_matrices,
        )

    raise InvalidPredictionError("AI がルールに合う番号を返しませんでした。もう一度お試しください")


def _to_predicted_sets(
    lottery: LotteryType,
    ai_sets: list[AiPredictedSet],
    count: int,
    draws: list[Draw],
) -> list[PredictedSet] | None:
    """AI の答えを検証し、過去結果との傾向スコア順に並べる。"""
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
        trend = candidate_trend(lottery, numbers, draws)
        sets.append(
            PredictedSet(
                numbers=numbers,
                reason=ai_set.reason,
                odds=calculate_odds(lottery, numbers),
                rank=0,
                trend_score=trend.score,
                average_distance=trend.average_distance,
                closest_round=trend.closest_round,
                closest_distance=trend.closest_distance,
                match_distribution=trend.match_distribution,
            )
        )
    sets.sort(key=lambda item: (-item.trend_score, item.numbers))
    return [
        item.model_copy(update={"rank": rank})
        for rank, item in enumerate(sets, start=1)
    ]


def build_prompt(
    rule: LotteryRule,
    stats: LotteryStats,
    count: int = 1,
    frequency_matrices: list[FrequencyMatrix] | None = None,
    cooccurrence_matrices: list[CooccurrenceMatrix] | None = None,
) -> str:
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
    if frequency_matrices and cooccurrence_matrices:
        lines.extend(
            _format_history_patterns(
                frequency_matrices,
                cooccurrence_matrices,
            )
        )
    return "\n".join(lines)


def _format_history_patterns(
    frequencies: list[FrequencyMatrix],
    cooccurrences: list[CooccurrenceMatrix],
) -> list[str]:
    """過去全期間の頻度と、件数・分母つきの上位共起ペアをAI用に整形する。"""
    lines = [
        "",
        "[DBに保存されている全期間の履歴分析]",
        "以下は過去の観測値であり、次回の当せん確率や番号同士の将来の関係を示すものではない。",
    ]
    for matrix in frequencies:
        lines.append(f"{matrix.title}（全{matrix.total_draws}回）")
        lines.append(
            ",".join(
                f"{label}:{count}"
                for label, count in zip(matrix.labels, matrix.counts)
            )
        )

    for matrix in cooccurrences:
        pairs = []
        is_unordered_pair_matrix = "本数字ペア" in matrix.title
        for row_index, row in enumerate(matrix.counts):
            for column_index, count in enumerate(row):
                if count == 0 or (
                    is_unordered_pair_matrix and row_index >= column_index
                ):
                    continue
                denominator = matrix.row_draw_counts[row_index]
                pairs.append(
                    (
                        count,
                        row_index,
                        column_index,
                        denominator,
                        matrix.probabilities[row_index][column_index],
                    )
                )
        pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
        lines.append(f"{matrix.title}（観測回数の多い上位10組）")
        lines.append("行番号/桁の値,列番号/桁の値,同時出現回数,行の番号が出た回数,行内割合")
        for count, row_index, column_index, denominator, probability in pairs[:10]:
            lines.append(
                f"{matrix.row_labels[row_index]},{matrix.column_labels[column_index]},"
                f"{count},{denominator},{probability:.4f}"
            )
    return lines


def _format_stat(stat: NumberStat) -> str:
    """番号1つの集計を、AI に渡す1行の文字にする"""
    gap = "未出" if stat.gap is None else str(stat.gap)
    return f"{stat.number},{stat.count},{gap}"
