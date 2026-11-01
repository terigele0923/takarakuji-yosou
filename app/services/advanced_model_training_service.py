import calendar
import datetime
import hashlib
import itertools
import json
import math
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from app.config import DB_PATH
from app.schemas.lottery import Draw, LotteryType
from app.services.bias_prediction_service import (
    DEFAULT_CONFIG,
    BiasPredictionConfig,
    build_bias_model,
    score_candidate,
)
from app.services.lottery_data import load_draws
from app.services.model_profile_service import load_model_profile

CANDIDATES = tuple(itertools.product(range(10), repeat=3))


@dataclass(frozen=True)
class PeriodMetrics:
    evaluated_draws: int
    mean_actual_rank: float
    mean_rank_percentile: float
    average_best_matches: float
    random_average_best_matches: float
    match_lift: float
    confidence_low: float
    confidence_high: float
    exact_hits: int


class FeatureCache:
    def __init__(self, draws: list[Draw]):
        self.draws = draws
        self.values: dict[tuple[int, int], np.ndarray] = {}
        self.random_averages: dict[tuple[int, int], float] = {}

    def get(self, draw_index: int, half_life: int) -> np.ndarray:
        key = (draw_index, half_life)
        if key not in self.values:
            config = replace(DEFAULT_CONFIG, recent_half_life=half_life)
            model = build_bias_model(
                LotteryType.NUMBERS3, self.draws[:draw_index], config
            )
            self.values[key] = np.asarray(
                [
                    (
                        scored.long_score,
                        scored.recent_score,
                        scored.pair_score,
                    )
                    for numbers in CANDIDATES
                    for scored in [score_candidate(model, numbers, config)]
                ],
                dtype=np.float64,
            )
        return self.values[key]

    def random_average(self, actual: Draw, samples: int) -> float:
        key = (actual.round, samples)
        if key not in self.random_averages:
            self.random_averages[key] = _random_average(actual, samples)
        return self.random_averages[key]


def train_numbers3_with_holdouts(
    db_path: Path = DB_PATH,
    report_path: Path | None = None,
    folds: int = 5,
    validation_months: int = 12,
    test_months: int = 3,
    half_lives: tuple[int, ...] = (10, 20, 40, 80, 160),
    weight_step: float = 0.05,
    random_samples: int = 200,
    bootstrap_samples: int = 2_000,
) -> dict:
    """5つの未使用期間で候補モデルを評価し、基準合格時だけ本番へ昇格する。"""
    _validate_options(
        folds,
        validation_months,
        test_months,
        half_lives,
        weight_step,
        random_samples,
        bootstrap_samples,
    )
    draws = load_draws(LotteryType.NUMBERS3, db_path)
    if len(draws) < 100:
        raise ValueError("高度学習にはナンバーズ3の抽選結果が100回以上必要です")
    cache = FeatureCache(draws)
    weights = _weight_matrix(weight_step)
    current_profile = load_model_profile(LotteryType.NUMBERS3, db_path)
    latest_date = draws[-1].draw_date
    fold_reports = []
    challenger_results = []
    champion_results = []

    for offset in reversed(range(folds)):
        test_end = _subtract_months(latest_date, offset * test_months)
        test_start = _subtract_months(test_end, test_months)
        validation_start = _subtract_months(test_start, validation_months)
        validation_indices = _indices_between(
            draws, validation_start, test_start
        )
        test_indices = _indices_between(draws, test_start, test_end)
        if not validation_indices or not test_indices:
            raise ValueError("指定期間に十分な検証データがありません")

        challenger = _tune_config(
            draws, cache, validation_indices, weights, half_lives
        )
        challenger_period = _evaluate_config(
            draws,
            cache,
            test_indices,
            challenger,
            random_samples,
        )
        champion_period = _evaluate_config(
            draws,
            cache,
            test_indices,
            current_profile.config,
            random_samples,
        )
        challenger_results.extend(challenger_period)
        champion_results.extend(champion_period)
        fold_reports.append(
            {
                "validation_start": validation_start.isoformat(),
                "validation_end": test_start.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "validation_draws": len(validation_indices),
                "test_draws": len(test_indices),
                "selected_config": _config_dict(challenger),
                "challenger": asdict(
                    _summarize(challenger_period, bootstrap_samples)
                ),
                "champion": asdict(
                    _summarize(champion_period, bootstrap_samples)
                ),
            }
        )

    challenger_metrics = _summarize(challenger_results, bootstrap_samples)
    champion_metrics = _summarize(champion_results, bootstrap_samples)
    final_validation_start = _subtract_months(latest_date, validation_months)
    final_indices = _indices_between(draws, final_validation_start, latest_date)
    final_config = _tune_config(draws, cache, final_indices, weights, half_lives)
    promoted = (
        challenger_metrics.mean_actual_rank < champion_metrics.mean_actual_rank
        and challenger_metrics.mean_rank_percentile < 0.5
        and challenger_metrics.confidence_low > 0
    )
    created_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    report = {
        "lottery": LotteryType.NUMBERS3.value,
        "created_at": created_at,
        "folds": folds,
        "validation_months": validation_months,
        "test_months": test_months,
        "weight_step": weight_step,
        "half_lives": list(half_lives),
        "promotion_rule": {
            "better_rank_than_champion": True,
            "rank_percentile_below": 0.5,
            "match_lift_confidence_low_above": 0,
        },
        "previous_champion": {
            "model_version": current_profile.model_version,
            "config": _config_dict(current_profile.config),
            "metrics": asdict(champion_metrics),
        },
        "challenger": {
            "config": _config_dict(final_config),
            "metrics": asdict(challenger_metrics),
        },
        "fold_results": fold_reports,
        "promoted": promoted,
    }
    digest = hashlib.sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    candidate_version = (
        f"bias-v2-advanced-{digest[:8]}-h{final_config.recent_half_life}"
    )
    report["challenger"]["model_version"] = candidate_version
    report_json = json.dumps(report, ensure_ascii=False, indent=2)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO model_training_runs (
                lottery, created_at, folds, validation_months, test_months,
                candidate_model_version, long_weight, recent_weight, pair_weight,
                recent_half_life, evaluated_draws, mean_actual_rank,
                mean_rank_percentile, average_best_matches,
                random_average_best_matches, match_lift, confidence_low,
                confidence_high, exact_hits, promoted, report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                LotteryType.NUMBERS3.value,
                created_at,
                folds,
                validation_months,
                test_months,
                candidate_version,
                final_config.long_weight,
                final_config.recent_weight,
                final_config.pair_weight,
                final_config.recent_half_life,
                challenger_metrics.evaluated_draws,
                challenger_metrics.mean_actual_rank,
                challenger_metrics.mean_rank_percentile,
                challenger_metrics.average_best_matches,
                challenger_metrics.random_average_best_matches,
                challenger_metrics.match_lift,
                challenger_metrics.confidence_low,
                challenger_metrics.confidence_high,
                challenger_metrics.exact_hits,
                int(promoted),
                report_json,
            ),
        )
        if promoted:
            connection.execute(
                """
                INSERT INTO bias_model_profiles (
                    lottery, model_version, long_weight, recent_weight, pair_weight,
                    recent_half_life, learned_at, source_report_hash,
                    training_rounds, training_exact_hits, training_total_matches
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lottery) DO UPDATE SET
                    model_version=excluded.model_version,
                    long_weight=excluded.long_weight,
                    recent_weight=excluded.recent_weight,
                    pair_weight=excluded.pair_weight,
                    recent_half_life=excluded.recent_half_life,
                    learned_at=excluded.learned_at,
                    source_report_hash=excluded.source_report_hash,
                    training_rounds=excluded.training_rounds,
                    training_exact_hits=excluded.training_exact_hits,
                    training_total_matches=excluded.training_total_matches
                """,
                (
                    LotteryType.NUMBERS3.value,
                    candidate_version,
                    final_config.long_weight,
                    final_config.recent_weight,
                    final_config.pair_weight,
                    final_config.recent_half_life,
                    created_at,
                    digest,
                    challenger_metrics.evaluated_draws,
                    challenger_metrics.exact_hits,
                    round(
                        challenger_metrics.average_best_matches
                        * challenger_metrics.evaluated_draws
                    ),
                ),
            )

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_json, encoding="utf-8")
    return report


def train_numbers3_iteratively(
    db_path: Path = DB_PATH,
    report_path: Path | None = None,
    loops: int = 5,
    learning_start: datetime.date = datetime.date(2016, 1, 1),
    learning_end: datetime.date = datetime.date(2025, 12, 31),
    test_start: datetime.date = datetime.date(2026, 1, 1),
    test_end: datetime.date | None = None,
    random_samples: int = 200,
    bootstrap_samples: int = 2_000,
) -> dict:
    """外れを分析して局所調整する処理を繰り返し、未使用期間で最終判定する。"""
    if min(loops, random_samples, bootstrap_samples) <= 0:
        raise ValueError("ループ回数と標本数は正数で指定してください")
    if learning_start > learning_end or test_start > (test_end or datetime.date.max):
        raise ValueError("学習・テスト期間の開始日と終了日が逆です")
    if learning_end >= test_start:
        raise ValueError("学習期間とテスト期間は分離してください")
    draws = load_draws(LotteryType.NUMBERS3, db_path)
    if len(draws) < 100:
        raise ValueError("反復学習にはナンバーズ3の抽選結果が100回以上必要です")
    latest_date = draws[-1].draw_date
    effective_test_end = min(test_end or latest_date, latest_date)
    learning_indices = _indices_inclusive(draws, learning_start, learning_end)
    test_indices = _indices_inclusive(draws, test_start, effective_test_end)
    if not learning_indices or not test_indices:
        raise ValueError("指定期間に十分な学習・最終テストデータがありません")

    cache = FeatureCache(draws)
    champion = load_model_profile(LotteryType.NUMBERS3, db_path)
    current = champion.config
    loop_reports = []
    for loop_number in range(1, loops + 1):
        before_results = _evaluate_config(
            draws, cache, learning_indices, current, random_samples
        )
        loss_rounds = {
            item["round"] for item in before_results if not item["exact_hit"]
        }
        candidates = _neighbor_configs(current)
        evaluated = [
            (
                candidate,
                _evaluate_config(
                    draws, cache, learning_indices, candidate, random_samples
                ),
            )
            for candidate in candidates
        ]
        selected, selected_results = max(
            evaluated,
            key=lambda item: _iteration_quality(
                item[1], loss_rounds, item[0], champion.config
            ),
        )
        recovered = sum(
            item["exact_hit"] and item["round"] in loss_rounds
            for item in selected_results
        )
        loop_reports.append(
            {
                "loop": loop_number,
                "losses_analyzed": len(loss_rounds),
                "candidates_compared": len(candidates),
                "before_config": _config_dict(current),
                "before_metrics": asdict(_summarize(before_results, 200)),
                "selected_config": _config_dict(selected),
                "after_metrics": asdict(_summarize(selected_results, 200)),
                "losses_recovered_as_exact": recovered,
                "changed": selected != current,
            }
        )
        current = selected

    challenger_test = _evaluate_config(
        draws, cache, test_indices, current, random_samples
    )
    champion_test = _evaluate_config(
        draws, cache, test_indices, champion.config, random_samples
    )
    challenger_metrics = _summarize(challenger_test, bootstrap_samples)
    champion_metrics = _summarize(champion_test, bootstrap_samples)
    promoted = (
        challenger_metrics.mean_actual_rank < champion_metrics.mean_actual_rank
        and challenger_metrics.mean_rank_percentile < 0.5
        and challenger_metrics.confidence_low > 0
    )
    created_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    report = {
        "lottery": LotteryType.NUMBERS3.value,
        "created_at": created_at,
        "method": "iterative_loss_feedback",
        "loops": loops,
        "learning_months": _calendar_months(learning_start, learning_end),
        "test_months": _calendar_months(test_start, effective_test_end),
        "learning_period": {
            "start": learning_start.isoformat(),
            "end": learning_end.isoformat(),
            "draws": len(learning_indices),
        },
        "untouched_test_period": {
            "start": test_start.isoformat(),
            "end": effective_test_end.isoformat(),
            "draws": len(test_indices),
        },
        "loop_results": loop_reports,
        "previous_champion": {
            "model_version": champion.model_version,
            "config": _config_dict(champion.config),
            "metrics": asdict(champion_metrics),
        },
        "challenger": {
            "config": _config_dict(current),
            "metrics": asdict(challenger_metrics),
        },
        "promotion_rule": {
            "better_rank_than_champion": True,
            "rank_percentile_below": 0.5,
            "match_lift_confidence_low_above": 0,
        },
        "promoted": promoted,
    }
    digest = hashlib.sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    candidate_version = (
        f"bias-v2-iterative-{digest[:8]}-h{current.recent_half_life}"
    )
    report["challenger"]["model_version"] = candidate_version
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    _save_iterative_run(
        db_path,
        report,
        report_json,
        candidate_version,
        current,
        challenger_metrics,
        created_at,
        digest,
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_json, encoding="utf-8")
    return report


def _neighbor_configs(config: BiasPredictionConfig) -> list[BiasPredictionConfig]:
    configs = {config}
    weights = [config.long_weight, config.recent_weight, config.pair_weight]
    step = 0.05
    for source in range(3):
        for target in range(3):
            if source == target or weights[source] < step - 1e-9:
                continue
            changed = weights.copy()
            changed[source] = round(changed[source] - step, 10)
            changed[target] = round(changed[target] + step, 10)
            configs.add(
                replace(
                    config,
                    long_weight=changed[0],
                    recent_weight=changed[1],
                    pair_weight=changed[2],
                )
            )
    half_lives = (10, 20, 40, 80, 160)
    nearest = min(range(len(half_lives)), key=lambda i: abs(half_lives[i] - config.recent_half_life))
    for index in (nearest - 1, nearest + 1):
        if 0 <= index < len(half_lives):
            configs.add(replace(config, recent_half_life=half_lives[index]))
    return sorted(
        configs,
        key=lambda item: (
            item.recent_half_life,
            item.long_weight,
            item.recent_weight,
            item.pair_weight,
        ),
    )


def _iteration_quality(
    results: list[dict],
    loss_rounds: set[int],
    config: BiasPredictionConfig,
    champion: BiasPredictionConfig,
) -> tuple:
    losses = [item for item in results if item["round"] in loss_rounds]
    exact_hits = sum(item["exact_hit"] for item in results)
    recovered = sum(item["exact_hit"] for item in losses)
    two_or_more = sum(item["best_matches"] >= 2 for item in losses)
    loss_matches = sum(item["best_matches"] for item in losses)
    mean_rank = sum(item["rank"] for item in results) / len(results)
    distance = (
        abs(config.long_weight - champion.long_weight)
        + abs(config.recent_weight - champion.recent_weight)
        + abs(config.pair_weight - champion.pair_weight)
        + abs(math.log2(config.recent_half_life / champion.recent_half_life)) * 0.05
    )
    return exact_hits, recovered, two_or_more, loss_matches, -mean_rank, -distance


def _save_iterative_run(
    db_path: Path,
    report: dict,
    report_json: str,
    candidate_version: str,
    config: BiasPredictionConfig,
    metrics: PeriodMetrics,
    created_at: str,
    digest: str,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO model_training_runs (
                lottery, created_at, folds, validation_months, test_months,
                candidate_model_version, long_weight, recent_weight, pair_weight,
                recent_half_life, evaluated_draws, mean_actual_rank,
                mean_rank_percentile, average_best_matches,
                random_average_best_matches, match_lift, confidence_low,
                confidence_high, exact_hits, promoted, report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                LotteryType.NUMBERS3.value,
                created_at,
                report["loops"],
                report["learning_months"],
                report["test_months"],
                candidate_version,
                config.long_weight,
                config.recent_weight,
                config.pair_weight,
                config.recent_half_life,
                metrics.evaluated_draws,
                metrics.mean_actual_rank,
                metrics.mean_rank_percentile,
                metrics.average_best_matches,
                metrics.random_average_best_matches,
                metrics.match_lift,
                metrics.confidence_low,
                metrics.confidence_high,
                metrics.exact_hits,
                int(report["promoted"]),
                report_json,
            ),
        )
        if report["promoted"]:
            connection.execute(
                """
                INSERT INTO bias_model_profiles (
                    lottery, model_version, long_weight, recent_weight, pair_weight,
                    recent_half_life, learned_at, source_report_hash,
                    training_rounds, training_exact_hits, training_total_matches
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lottery) DO UPDATE SET
                    model_version=excluded.model_version,
                    long_weight=excluded.long_weight,
                    recent_weight=excluded.recent_weight,
                    pair_weight=excluded.pair_weight,
                    recent_half_life=excluded.recent_half_life,
                    learned_at=excluded.learned_at,
                    source_report_hash=excluded.source_report_hash,
                    training_rounds=excluded.training_rounds,
                    training_exact_hits=excluded.training_exact_hits,
                    training_total_matches=excluded.training_total_matches
                """,
                (
                    LotteryType.NUMBERS3.value,
                    candidate_version,
                    config.long_weight,
                    config.recent_weight,
                    config.pair_weight,
                    config.recent_half_life,
                    created_at,
                    digest,
                    metrics.evaluated_draws,
                    metrics.exact_hits,
                    round(metrics.average_best_matches * metrics.evaluated_draws),
                ),
            )


def _tune_config(
    draws: list[Draw],
    cache: FeatureCache,
    indices: list[int],
    weights: np.ndarray,
    half_lives: tuple[int, ...],
) -> BiasPredictionConfig:
    best_key = None
    best_config = None
    for half_life in half_lives:
        rank_totals = np.zeros(len(weights), dtype=np.float64)
        for index in indices:
            features = cache.get(index, half_life)
            scores = features @ weights.T
            actual_index = _candidate_index(draws[index].numbers)
            actual_scores = scores[actual_index]
            rank_totals += np.sum(scores > actual_scores, axis=0) + 1
        mean_ranks = rank_totals / len(indices)
        for weight_index, weight in enumerate(weights):
            distance = float(np.sum(np.abs(weight - np.asarray([0.3, 0.5, 0.2]))))
            key = (float(mean_ranks[weight_index]) + 5 * distance, distance)
            if best_key is None or key < best_key:
                best_key = key
                best_config = replace(
                    DEFAULT_CONFIG,
                    recent_half_life=half_life,
                    long_weight=float(weight[0]),
                    recent_weight=float(weight[1]),
                    pair_weight=float(weight[2]),
                )
    assert best_config is not None
    return best_config


def _evaluate_config(
    draws: list[Draw],
    cache: FeatureCache,
    indices: list[int],
    config: BiasPredictionConfig,
    random_samples: int,
) -> list[dict]:
    weight = np.asarray(
        [config.long_weight, config.recent_weight, config.pair_weight]
    )
    results = []
    for index in indices:
        features = cache.get(index, config.recent_half_life)
        raw_scores = features @ weight
        actual = draws[index]
        actual_index = _candidate_index(actual.numbers)
        rank = int(np.sum(raw_scores > raw_scores[actual_index]) + 1)
        selected = _select_five(raw_scores)
        best_matches = max(
            sum(left == right for left, right in zip(numbers, actual.numbers))
            for numbers in selected
        )
        random_average = cache.random_average(actual, random_samples)
        results.append(
            {
                "round": actual.round,
                "rank": rank,
                "best_matches": best_matches,
                "random_average": random_average,
                "difference": best_matches - random_average,
                "exact_hit": best_matches == 3,
            }
        )
    return results


def _select_five(raw_scores: np.ndarray) -> list[tuple[int, int, int]]:
    selected = []
    for candidate_index in np.argsort(-raw_scores, kind="stable"):
        numbers = CANDIDATES[int(candidate_index)]
        if all(
            sum(left == right for left, right in zip(numbers, other)) <= 1
            for other in selected
        ):
            selected.append(numbers)
            if len(selected) == 5:
                break
    return selected


def _random_average(actual: Draw, samples: int) -> float:
    seed = int.from_bytes(
        hashlib.sha256(f"numbers3:{actual.round}:advanced".encode()).digest()[:8]
    )
    rng = np.random.default_rng(seed)
    portfolios = rng.integers(0, 10, size=(samples, 5, 3))
    actual_array = np.asarray(actual.numbers)
    matches = np.sum(portfolios == actual_array, axis=2)
    return float(np.mean(np.max(matches, axis=1)))


def _summarize(results: list[dict], bootstrap_samples: int) -> PeriodMetrics:
    differences = np.asarray([item["difference"] for item in results])
    rng = np.random.default_rng(20261101)
    bootstrap = np.mean(
        rng.choice(differences, size=(bootstrap_samples, len(differences)), replace=True),
        axis=1,
    )
    ranks = np.asarray([item["rank"] for item in results])
    matches = np.asarray([item["best_matches"] for item in results])
    random_matches = np.asarray([item["random_average"] for item in results])
    return PeriodMetrics(
        evaluated_draws=len(results),
        mean_actual_rank=round(float(np.mean(ranks)), 4),
        mean_rank_percentile=round(float(np.mean(ranks) / 1000), 6),
        average_best_matches=round(float(np.mean(matches)), 4),
        random_average_best_matches=round(float(np.mean(random_matches)), 4),
        match_lift=round(float(np.mean(differences)), 4),
        confidence_low=round(float(np.quantile(bootstrap, 0.025)), 4),
        confidence_high=round(float(np.quantile(bootstrap, 0.975)), 4),
        exact_hits=int(sum(item["exact_hit"] for item in results)),
    )


def _weight_matrix(step: float) -> np.ndarray:
    units = round(1 / step)
    return np.asarray(
        [
            (long / units, recent / units, (units - long - recent) / units)
            for long in range(units + 1)
            for recent in range(units - long + 1)
        ],
        dtype=np.float64,
    )


def _indices_between(
    draws: list[Draw], start: datetime.date, end: datetime.date
) -> list[int]:
    return [
        index
        for index, draw in enumerate(draws)
        if start < draw.draw_date <= end
    ]


def _indices_inclusive(
    draws: list[Draw], start: datetime.date, end: datetime.date
) -> list[int]:
    return [
        index
        for index, draw in enumerate(draws)
        if start <= draw.draw_date <= end
    ]


def _calendar_months(start: datetime.date, end: datetime.date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _candidate_index(numbers: list[int]) -> int:
    return numbers[0] * 100 + numbers[1] * 10 + numbers[2]


def _config_dict(config: BiasPredictionConfig) -> dict:
    return {
        "long_weight": config.long_weight,
        "recent_weight": config.recent_weight,
        "pair_weight": config.pair_weight,
        "recent_half_life": config.recent_half_life,
    }


def _subtract_months(value: datetime.date, months: int) -> datetime.date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def _validate_options(
    folds: int,
    validation_months: int,
    test_months: int,
    half_lives: tuple[int, ...],
    weight_step: float,
    random_samples: int,
    bootstrap_samples: int,
) -> None:
    if min(folds, validation_months, test_months, random_samples, bootstrap_samples) <= 0:
        raise ValueError("学習回数と期間、標本数は正数で指定してください")
    if not half_lives or min(half_lives) <= 0:
        raise ValueError("半減期候補は正数で指定してください")
    units = 1 / weight_step
    if not math.isclose(units, round(units)):
        raise ValueError("重み刻みは1を割り切れる値にしてください")
