from app.schemas.lottery import RULES, LotteryType
from app.schemas.predict import BiasBacktest, PredictedSet, PredictResponse
from app.services.bias_prediction_service import (
    DEFAULT_CONFIG,
    MODEL_VERSION,
    BiasPredictionConfig,
    backtest_bias,
    build_bias_model,
    describe_candidate,
    generate_candidates,
    normalize_scores,
)
from app.services.lottery_data import load_draws
from app.services.odds_service import calculate_odds
from app.services.stats_service import calculate_stats
from app.services.trend_service import build_history_matrices, candidate_trend


class NoDrawDataError(Exception):
    """抽選結果のデータがまだないときのエラー"""


def predict(
    lottery: LotteryType,
    count: int = 1,
    config: BiasPredictionConfig = DEFAULT_CONFIG,
    model_version: str = MODEL_VERSION,
) -> PredictResponse:
    """過去の長期・直近・ペアの偏りを推定し、上位候補を返す。"""
    rule = RULES[lottery]
    draws = load_draws(lottery)
    if not draws:
        raise NoDrawDataError(f"{rule.name}の抽選結果がまだありません")

    stats = calculate_stats(lottery, draws)
    frequency_matrices, cooccurrence_matrices = build_history_matrices(lottery, draws)
    model = build_bias_model(lottery, draws, config)
    candidates = generate_candidates(model, count, config)
    display_scores = normalize_scores(candidates)
    sets = []
    for rank, (candidate, display_score) in enumerate(zip(candidates, display_scores), start=1):
        numbers = list(candidate.numbers)
        trend = candidate_trend(lottery, numbers, draws)
        sets.append(
            PredictedSet(
                numbers=numbers,
                reason=describe_candidate(candidate),
                odds=calculate_odds(lottery, numbers),
                rank=rank,
                bias_score=display_score,
                bias_components={
                    "long_term": round(candidate.long_score, 4),
                    "recent": round(candidate.recent_score, 4),
                    "pair": round(candidate.pair_score, 4),
                },
                trend_score=trend.score,
                average_distance=trend.average_distance,
                closest_round=trend.closest_round,
                closest_distance=trend.closest_distance,
                match_distribution=trend.match_distribution,
            )
        )

    backtest = backtest_bias(lottery, draws, config)
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
        trend_metric="桁位置つきHamming距離" if rule.by_position else "番号集合のJaccard距離",
        trend_draw_count=len(draws),
        trend_first_date=min(draw.draw_date for draw in draws),
        trend_last_date=max(draw.draw_date for draw in draws),
        frequency_matrices=frequency_matrices,
        cooccurrence_matrices=cooccurrence_matrices,
        prediction_method=(
            f"長期頻度{config.long_weight:.0%}・"
            f"時間加重直近頻度{config.recent_weight:.0%}・"
            f"ペア共起{config.pair_weight:.0%}"
        ),
        backtest=BiasBacktest(**backtest.__dict__),
        model_version=model_version,
    )
