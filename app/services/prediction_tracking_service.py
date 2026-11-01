import datetime
import json
import sqlite3
from pathlib import Path

from app.config import DB_PATH
from app.schemas.lottery import LotteryType
from app.schemas.predict import PredictResponse
from app.schemas.prediction_tracking import ModelEvaluation, SavedPrediction
from app.services.bias_prediction_service import MODEL_VERSION, backtest_bias
from app.services.lottery_data import load_draws


def save_prediction(
    result: PredictResponse,
    db_path: Path = DB_PATH,
) -> SavedPrediction:
    """予想APIの出力を、使用した抽選データの版と一緒に保存する。"""
    generated_at = _now()
    payload = result.model_dump_json()
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO prediction_runs (
                lottery, target_round, source_last_round, source_draw_count,
                requested_count, generated_at, model_version, response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.lottery.value,
                result.next_round,
                result.last_round,
                result.total_draws,
                len(result.sets),
                generated_at.isoformat(),
                MODEL_VERSION,
                payload,
            ),
        )
        prediction_id = cursor.lastrowid
    return SavedPrediction(
        id=prediction_id,
        generated_at=generated_at,
        model_version=MODEL_VERSION,
        result=result,
    )


def list_predictions(
    lottery: LotteryType | None = None,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> list[SavedPrediction]:
    where = "WHERE lottery = ?" if lottery else ""
    parameters: tuple[object, ...] = (lottery.value, limit) if lottery else (limit,)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT id, generated_at, model_version, response_json
            FROM prediction_runs
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    return [
        SavedPrediction(
            id=row["id"],
            generated_at=row["generated_at"],
            model_version=row["model_version"],
            result=PredictResponse.model_validate(json.loads(row["response_json"])),
        )
        for row in rows
    ]


def evaluate_pending(db_path: Path = DB_PATH) -> list[ModelEvaluation]:
    """最終抽選回がまだ評価されていない種類だけをバックテストして保存する。"""
    saved = []
    for lottery in LotteryType:
        draws = load_draws(lottery, db_path)
        if not draws:
            continue
        source_last_round = draws[-1].round
        with sqlite3.connect(db_path) as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM model_evaluations
                WHERE lottery = ? AND source_last_round = ? AND model_version = ?
                """,
                (lottery.value, source_last_round, MODEL_VERSION),
            ).fetchone()
        if exists:
            continue

        result = backtest_bias(lottery, draws)
        evaluated_at = _now()
        with sqlite3.connect(db_path) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO model_evaluations (
                    lottery, source_last_round, source_draw_count, evaluated_at,
                    model_version, evaluated_draws, actual_average_score,
                    random_average_score, score_lift_percent, above_random_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lottery.value,
                    source_last_round,
                    len(draws),
                    evaluated_at.isoformat(),
                    MODEL_VERSION,
                    result.evaluated_draws,
                    result.actual_average_score,
                    result.random_average_score,
                    result.score_lift_percent,
                    result.above_random_rate,
                ),
            )
            evaluation_id = cursor.lastrowid
        if evaluation_id:
            saved.append(
                ModelEvaluation(
                    id=evaluation_id,
                    lottery=lottery,
                    source_last_round=source_last_round,
                    source_draw_count=len(draws),
                    evaluated_at=evaluated_at,
                    model_version=MODEL_VERSION,
                    **result.__dict__,
                )
            )
    return saved


def list_evaluations(
    lottery: LotteryType | None = None,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> list[ModelEvaluation]:
    where = "WHERE lottery = ?" if lottery else ""
    parameters: tuple[object, ...] = (lottery.value, limit) if lottery else (limit,)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT * FROM model_evaluations
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    return [ModelEvaluation(**dict(row)) for row in rows]


def _now() -> datetime.datetime:
    return datetime.datetime.now().astimezone().replace(microsecond=0)
