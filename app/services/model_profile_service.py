import datetime
import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from app.config import DB_PATH
from app.schemas.lottery import LotteryType
from app.services.bias_prediction_service import (
    DEFAULT_CONFIG,
    MODEL_VERSION,
    BiasPredictionConfig,
    build_bias_model,
    generate_candidates,
)
from app.services.lottery_data import load_draws


@dataclass(frozen=True)
class ModelProfile:
    lottery: LotteryType
    model_version: str
    config: BiasPredictionConfig
    training_rounds: int = 0
    training_exact_hits: int = 0
    training_total_matches: int = 0


def load_model_profile(
    lottery: LotteryType,
    db_path: Path = DB_PATH,
) -> ModelProfile:
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM bias_model_profiles WHERE lottery = ?",
                (lottery.value,),
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        return ModelProfile(lottery, MODEL_VERSION, DEFAULT_CONFIG)
    config = replace(
        DEFAULT_CONFIG,
        recent_half_life=row["recent_half_life"],
        long_weight=row["long_weight"],
        recent_weight=row["recent_weight"],
        pair_weight=row["pair_weight"],
    )
    return ModelProfile(
        lottery=lottery,
        model_version=row["model_version"],
        config=config,
        training_rounds=row["training_rounds"],
        training_exact_hits=row["training_exact_hits"],
        training_total_matches=row["training_total_matches"],
    )


def learn_numbers3_profile(
    report_path: Path,
    db_path: Path = DB_PATH,
) -> ModelProfile:
    """前回の逐次評価期間から、ナンバーズ3の3成分重みをグリッド探索する。"""
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes.decode("utf-8"))
    if Path(report["source_database"]).resolve() != db_path.resolve():
        raise ValueError("評価レポートの元DBと学習先DBが一致しません")
    cutoff = datetime.date.fromisoformat(report["cutoff_date"])
    all_draws = load_draws(LotteryType.NUMBERS3, db_path)
    actual_by_round = {draw.round: draw for draw in all_draws}
    steps = [step for step in report["steps"] if step["lottery"] == "numbers3"]
    if not steps:
        raise ValueError("レポートにナンバーズ3の評価結果がありません")
    training = [draw for draw in all_draws if draw.draw_date <= cutoff]
    configs = _weight_configs()
    scores = {config: [0, 0, 0] for config in configs}

    for step in steps:
        actual = actual_by_round[int(step["round"])]
        model = build_bias_model(LotteryType.NUMBERS3, training)
        for config in configs:
            candidates = generate_candidates(model, 5, config)
            best_matches = max(
                sum(left == right for left, right in zip(candidate.numbers, actual.numbers))
                for candidate in candidates
            )
            scores[config][0] += best_matches == 3
            scores[config][1] += best_matches >= 2
            scores[config][2] += best_matches
        training.append(actual)

    best = max(
        configs,
        key=lambda config: (
            *scores[config],
            -_default_distance(config),
        ),
    )
    exact_hits, _two_or_more, total_matches = scores[best]
    digest = hashlib.sha256(report_bytes).hexdigest()
    version = (
        f"{MODEL_VERSION}-learned-{digest[:8]}-"
        f"{int(best.long_weight * 10)}{int(best.recent_weight * 10)}"
        f"{int(best.pair_weight * 10)}"
    )
    learned_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO bias_model_profiles (
                lottery, model_version, long_weight, recent_weight, pair_weight,
                recent_half_life, learned_at, source_report_hash, training_rounds,
                training_exact_hits, training_total_matches
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
                version,
                best.long_weight,
                best.recent_weight,
                best.pair_weight,
                best.recent_half_life,
                learned_at,
                digest,
                len(steps),
                exact_hits,
                total_matches,
            ),
        )
    return ModelProfile(
        lottery=LotteryType.NUMBERS3,
        model_version=version,
        config=best,
        training_rounds=len(steps),
        training_exact_hits=exact_hits,
        training_total_matches=total_matches,
    )


def _weight_configs() -> list[BiasPredictionConfig]:
    return [
        replace(
            DEFAULT_CONFIG,
            long_weight=long / 10,
            recent_weight=recent / 10,
            pair_weight=(10 - long - recent) / 10,
        )
        for long in range(11)
        for recent in range(11 - long)
    ]


def _default_distance(config: BiasPredictionConfig) -> float:
    return (
        abs(config.long_weight - DEFAULT_CONFIG.long_weight)
        + abs(config.recent_weight - DEFAULT_CONFIG.recent_weight)
        + abs(config.pair_weight - DEFAULT_CONFIG.pair_weight)
    )
