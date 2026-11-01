import calendar
import datetime
import hashlib
import json
import random
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from app.schemas.lottery import RULES, Draw, LotteryType
from app.services.bias_prediction_service import (
    build_bias_model,
    generate_candidates,
    normalize_scores,
)
from app.services.lottery_data import load_draws, save_draws
from app.services.model_profile_service import load_model_profile


@dataclass(frozen=True)
class WalkForwardStep:
    lottery: str
    round: int
    draw_date: str
    predicted_numbers: list[list[int]]
    bias_scores: list[float]
    winning_numbers: list[int]
    bonus_numbers: list[int]
    best_main_matches: int
    best_bonus_matches: int
    exact_hit: bool
    random_average_best_matches: float
    model_version: str


@dataclass(frozen=True)
class WalkForwardSummary:
    lottery: str
    evaluated_rounds: int
    prediction_count: int
    average_best_matches: float
    random_average_best_matches: float
    match_lift: float
    above_random_rate: float
    exact_hits: int


def run_walk_forward_evaluation(
    source_db: Path,
    mock_db: Path,
    report_path: Path,
    months: int = 2,
    prediction_count: int = 1,
    random_samples: int = 200,
    lotteries: list[LotteryType] | None = None,
) -> dict:
    """実DBのコピーを過去へ戻し、1回ずつ未来を開示してモデルを評価する。"""
    _validate_arguments(
        source_db, mock_db, report_path, months, prediction_count, random_samples
    )
    latest_date = _latest_draw_date(source_db)
    cutoff_date = _subtract_months(latest_date, months)
    withheld = _create_rolled_back_copy(source_db, mock_db, cutoff_date)

    steps: list[WalkForwardStep] = []
    summaries = []
    selected_lotteries = lotteries or list(LotteryType)
    for lottery in selected_lotteries:
        lottery_steps = _evaluate_lottery(
            lottery,
            withheld.get(lottery, []),
            mock_db,
            prediction_count,
            random_samples,
        )
        steps.extend(lottery_steps)
        summaries.append(_summarize(lottery, lottery_steps, prediction_count))

    report = {
        "model_version": (
            steps[0].model_version if len({step.model_version for step in steps}) == 1
            else "mixed"
        ),
        "source_database": str(source_db.resolve()),
        "mock_database": str(mock_db.resolve()),
        "latest_date": latest_date.isoformat(),
        "cutoff_date": cutoff_date.isoformat(),
        "months": months,
        "prediction_count": prediction_count,
        "random_samples_per_round": random_samples,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "summaries": [asdict(summary) for summary in summaries],
        "steps": [asdict(step) for step in steps],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _evaluate_lottery(
    lottery: LotteryType,
    withheld: list[Draw],
    mock_db: Path,
    prediction_count: int,
    random_samples: int,
) -> list[WalkForwardStep]:
    training_draws = load_draws(lottery, mock_db)
    profile = load_model_profile(lottery, mock_db)
    steps = []
    for actual in withheld:
        model = build_bias_model(lottery, training_draws, profile.config)
        candidates = generate_candidates(model, prediction_count, profile.config)
        scores = normalize_scores(candidates)
        match_results = [
            _match(lottery, list(candidate.numbers), actual) for candidate in candidates
        ]
        best_main, best_bonus = max(match_results)
        random_average = _random_average_best_matches(
            lottery, actual, prediction_count, random_samples
        )
        steps.append(
            WalkForwardStep(
                lottery=lottery.value,
                round=actual.round,
                draw_date=actual.draw_date.isoformat(),
                predicted_numbers=[list(candidate.numbers) for candidate in candidates],
                bias_scores=scores,
                winning_numbers=actual.numbers,
                bonus_numbers=actual.bonus,
                best_main_matches=best_main,
                best_bonus_matches=best_bonus,
                exact_hit=best_main == RULES[lottery].count,
                random_average_best_matches=random_average,
                model_version=profile.model_version,
            )
        )
        save_draws(lottery, [actual], mock_db)
        training_draws.append(actual)
    return steps


def _create_rolled_back_copy(
    source_db: Path, mock_db: Path, cutoff_date: datetime.date
) -> dict[LotteryType, list[Draw]]:
    mock_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_db) as source, sqlite3.connect(mock_db) as target:
        source.backup(target)

    withheld: dict[LotteryType, list[Draw]] = {}
    with sqlite3.connect(mock_db) as connection:
        connection.row_factory = sqlite3.Row
        for lottery in LotteryType:
            rows = connection.execute(
                """
                SELECT round, draw_date, numbers, bonus FROM draws
                WHERE lottery = ? AND draw_date > ? ORDER BY round
                """,
                (lottery.value, cutoff_date.isoformat()),
            ).fetchall()
            withheld[lottery] = [_row_to_draw(row) for row in rows]

        connection.execute(
            """
            DELETE FROM prizes
            WHERE EXISTS (
                SELECT 1 FROM draws
                WHERE draws.lottery = prizes.lottery
                  AND draws.round = prizes.round
                  AND draws.draw_date > ?
            )
            """,
            (cutoff_date.isoformat(),),
        )
        connection.execute(
            "DELETE FROM draws WHERE draw_date > ?", (cutoff_date.isoformat(),)
        )
        connection.execute("DELETE FROM prediction_runs")
        connection.execute("DELETE FROM model_evaluations")
    return withheld


def _summarize(
    lottery: LotteryType,
    steps: list[WalkForwardStep],
    prediction_count: int,
) -> WalkForwardSummary:
    if not steps:
        return WalkForwardSummary(lottery.value, 0, prediction_count, 0, 0, 0, 0, 0)
    predicted_average = sum(step.best_main_matches for step in steps) / len(steps)
    random_average = sum(step.random_average_best_matches for step in steps) / len(steps)
    above_random = sum(
        step.best_main_matches > step.random_average_best_matches for step in steps
    )
    return WalkForwardSummary(
        lottery=lottery.value,
        evaluated_rounds=len(steps),
        prediction_count=prediction_count,
        average_best_matches=round(predicted_average, 4),
        random_average_best_matches=round(random_average, 4),
        match_lift=round(predicted_average - random_average, 4),
        above_random_rate=round(above_random / len(steps), 4),
        exact_hits=sum(step.exact_hit for step in steps),
    )


def _match(lottery: LotteryType, candidate: list[int], actual: Draw) -> tuple[int, int]:
    rule = RULES[lottery]
    main = (
        sum(left == right for left, right in zip(candidate, actual.numbers))
        if rule.by_position
        else len(set(candidate) & set(actual.numbers))
    )
    bonus = 0 if rule.by_position else len(set(candidate) & set(actual.bonus))
    return main, bonus


def _random_average_best_matches(
    lottery: LotteryType,
    actual: Draw,
    prediction_count: int,
    random_samples: int,
) -> float:
    seed = hashlib.sha256(f"{lottery.value}:{actual.round}:walk-forward".encode()).digest()
    rng = random.Random(int.from_bytes(seed[:8]))
    best_matches = []
    for _ in range(random_samples):
        candidates = [_random_candidate(lottery, rng) for _ in range(prediction_count)]
        best_matches.append(max(_match(lottery, item, actual)[0] for item in candidates))
    return round(sum(best_matches) / len(best_matches), 4)


def _random_candidate(lottery: LotteryType, rng: random.Random) -> list[int]:
    rule = RULES[lottery]
    values = list(range(rule.min, rule.max + 1))
    if rule.by_position:
        return [rng.choice(values) for _ in range(rule.count)]
    return sorted(rng.sample(values, rule.count))


def _row_to_draw(row: sqlite3.Row) -> Draw:
    return Draw(
        round=row["round"],
        draw_date=datetime.date.fromisoformat(row["draw_date"]),
        numbers=[int(value) for value in row["numbers"].split(",") if value],
        bonus=[int(value) for value in row["bonus"].split(",") if value],
    )


def _latest_draw_date(source_db: Path) -> datetime.date:
    with sqlite3.connect(source_db) as connection:
        row = connection.execute("SELECT MAX(draw_date) FROM draws").fetchone()
    if row is None or row[0] is None:
        raise ValueError("抽選データがありません")
    return datetime.date.fromisoformat(row[0])


def _subtract_months(value: datetime.date, months: int) -> datetime.date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def _validate_arguments(
    source_db: Path,
    mock_db: Path,
    report_path: Path,
    months: int,
    prediction_count: int,
    random_samples: int,
) -> None:
    if not source_db.is_file():
        raise FileNotFoundError(f"DBがありません: {source_db}")
    if source_db.resolve() == mock_db.resolve():
        raise ValueError("実DBとモックDBには別のパスを指定してください")
    if mock_db.exists() or report_path.exists():
        raise FileExistsError("モックDBまたはレポートが既に存在します。別名を指定してください")
    if months <= 0 or prediction_count <= 0 or random_samples <= 0:
        raise ValueError("月数、予想組数、ランダム比較回数は正数で指定してください")
