import datetime
import json
import sqlite3

import pytest

from app.db_migrations import upgrade_database
from app.schemas.lottery import Draw, LotteryType
from app.services.advanced_model_training_service import (
    train_numbers3_iteratively,
)
from app.services.lottery_data import save_draws
from app.services.model_profile_service import (
    learn_numbers3_profile,
    load_model_profile,
)
from app.services.walk_forward_evaluation_service import run_walk_forward_evaluation


def _draws(count: int) -> list[Draw]:
    return [
        Draw(
            round=index + 1,
            draw_date=datetime.date(2026, 1, 1) + datetime.timedelta(days=index * 7),
            numbers=sorted(
                [1, 5, 12, 19 + index % 5, 30 + index % 6, 38 + index % 6]
            ),
            bonus=[15],
        )
        for index in range(count)
    ]


def _numbers3_draws(count: int) -> list[Draw]:
    return [
        Draw(
            round=index + 1,
            draw_date=datetime.date(2026, 1, 1) + datetime.timedelta(days=index * 3),
            numbers=[(index + 2) % 10, (index * 3 + 1) % 10, (index * 7 + 4) % 10],
            bonus=[],
        )
        for index in range(count)
    ]


def test_実DBを変えずに二か月分を一回ずつ予想評価する(tmp_path):
    source_db = tmp_path / "source.db"
    mock_db = tmp_path / "mock.db"
    report_path = tmp_path / "report.json"
    upgrade_database(source_db)
    save_draws(LotteryType.LOTO6, _draws(40), source_db)

    report = run_walk_forward_evaluation(
        source_db,
        mock_db,
        report_path,
        months=2,
        prediction_count=2,
        random_samples=20,
    )

    loto6 = next(item for item in report["summaries"] if item["lottery"] == "loto6")
    steps = [item for item in report["steps"] if item["lottery"] == "loto6"]
    assert loto6["evaluated_rounds"] == len(steps) > 0
    assert all(len(item["predicted_numbers"]) == 2 for item in steps)
    assert all(item["round"] > 30 for item in steps)
    assert json.loads(report_path.read_text(encoding="utf-8"))["steps"] == report["steps"]

    with sqlite3.connect(source_db) as source, sqlite3.connect(mock_db) as mock:
        assert source.execute("SELECT COUNT(*) FROM draws").fetchone()[0] == 40
        assert mock.execute("SELECT COUNT(*) FROM draws").fetchone()[0] == 40


def test_実DBをモックDBとして上書きできない(tmp_path):
    source_db = tmp_path / "source.db"
    upgrade_database(source_db)
    save_draws(LotteryType.LOTO6, _draws(3), source_db)

    with pytest.raises(ValueError, match="別のパス"):
        run_walk_forward_evaluation(
            source_db,
            source_db,
            tmp_path / "report.json",
        )


def test_逐次評価結果からナンバーズ3の重みを学習して保存する(tmp_path):
    source_db = tmp_path / "source.db"
    mock_db = tmp_path / "mock.db"
    report_path = tmp_path / "report.json"
    upgrade_database(source_db)
    save_draws(LotteryType.NUMBERS3, _numbers3_draws(50), source_db)
    run_walk_forward_evaluation(
        source_db,
        mock_db,
        report_path,
        months=2,
        prediction_count=1,
        random_samples=5,
        lotteries=[LotteryType.NUMBERS3],
    )

    learned = learn_numbers3_profile(report_path, source_db)
    loaded = load_model_profile(LotteryType.NUMBERS3, source_db)

    assert learned.model_version.startswith("bias-v1-learned-")
    assert learned.training_rounds > 0
    assert loaded == learned
    assert round(
        learned.config.long_weight
        + learned.config.recent_weight
        + learned.config.pair_weight,
        10,
    ) == 1


def test_外れ分析と改善を指定回数繰り返して未使用期間で評価する(tmp_path):
    source_db = tmp_path / "source.db"
    report_path = tmp_path / "advanced.json"
    upgrade_database(source_db)
    save_draws(LotteryType.NUMBERS3, _numbers3_draws(220), source_db)

    report = train_numbers3_iteratively(
        db_path=source_db,
        report_path=report_path,
        loops=2,
        learning_start=datetime.date(2026, 1, 1),
        learning_end=datetime.date(2027, 3, 31),
        test_start=datetime.date(2027, 4, 1),
        test_end=datetime.date(2027, 10, 31),
        random_samples=10,
        bootstrap_samples=100,
    )

    assert report["method"] == "iterative_loss_feedback"
    assert len(report["loop_results"]) == 2
    assert all(item["losses_analyzed"] > 0 for item in report["loop_results"])
    assert report["untouched_test_period"]["draws"] > 0
    assert report["challenger"]["metrics"]["evaluated_draws"] > 0
    assert report_path.exists()
    with sqlite3.connect(source_db) as connection:
        saved = connection.execute(
            "SELECT folds, evaluated_draws, promoted FROM model_training_runs"
        ).fetchone()
    assert saved[0] == 2
    assert saved[1] == report["challenger"]["metrics"]["evaluated_draws"]
    assert saved[2] in (0, 1)
