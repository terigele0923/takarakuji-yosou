import datetime
import sqlite3
from unittest.mock import patch

from app.db_migrations import upgrade_database
from app.schemas.lottery import Draw, LotteryType
from app.services import predict_service
from app.services.lottery_data import save_draws
from app.services.prediction_tracking_service import (
    evaluate_pending,
    list_evaluations,
    list_predictions,
    save_prediction,
)


def make_draws(count: int) -> list[Draw]:
    return [
        Draw(
            round=index + 1,
            draw_date=datetime.date(2025, 1, 1) + datetime.timedelta(days=index * 3),
            numbers=sorted(
                [1, 5, 12, 19 + index % 5, 30 + index % 6, 38 + index % 6]
            ),
            bonus=[15],
        )
        for index in range(count)
    ]


def test_予想結果を使用データの版と一緒に保存して読み出せる(tmp_path):
    database_path = tmp_path / "tracking.db"
    upgrade_database(database_path)
    draws = make_draws(40)
    with patch("app.services.predict_service.load_draws", return_value=draws):
        result = predict_service.predict(LotteryType.LOTO6, 2)

    saved = save_prediction(result, database_path)
    history = list_predictions(LotteryType.LOTO6, db_path=database_path)

    assert saved.result.next_round == 41
    assert len(history) == 1
    assert history[0].result.sets == result.sets
    with sqlite3.connect(database_path) as connection:
        source = connection.execute(
            "SELECT source_last_round, source_draw_count FROM prediction_runs"
        ).fetchone()
    assert source == (40, 40)


def test_最新抽選回ごとに評価を一度だけ保存する(tmp_path):
    database_path = tmp_path / "evaluation.db"
    upgrade_database(database_path)
    draws = make_draws(35)
    save_draws(LotteryType.LOTO6, draws, database_path)

    first = evaluate_pending(database_path)
    repeated = evaluate_pending(database_path)
    save_draws(LotteryType.LOTO6, make_draws(36)[-1:], database_path)
    next_round = evaluate_pending(database_path)
    history = list_evaluations(LotteryType.LOTO6, db_path=database_path)

    assert [item.source_last_round for item in first] == [35]
    assert repeated == []
    assert [item.source_last_round for item in next_round] == [36]
    assert [item.source_last_round for item in history] == [36, 35]
    assert history[0].evaluated_draws == 6
