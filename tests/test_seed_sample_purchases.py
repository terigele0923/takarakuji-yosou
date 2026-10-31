import datetime
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import DEFAULT_DB_PATH
from app.schemas.lottery import Draw, LotteryType
from app.services.lottery_data import save_draws
from app.services.purchase_service import check_results
from scripts.seed_sample_data import seed
from scripts.seed_sample_purchases import LOST, PENDING, seed_purchases

CREATE_TABLES_SQL = Path(__file__).resolve().parent.parent / "scripts" / "create_tables.sql"


@pytest.fixture
def db_path(tmp_path):
    """一時フォルダにテスト専用の DB を作り、表を作る"""
    path = tmp_path / "sample.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(CREATE_TABLES_SQL.read_text(encoding="utf-8"))
    return path


def assert_results_match(db_path, purchases):
    """「結果を確認」したあとの結果が、出るはずの結果と一致するか確かめる"""
    records = sorted(check_results(db_path).purchases, key=lambda record: record.id)
    assert len(records) == len(purchases) == 20
    for record, (_, label) in zip(records, purchases):
        if label == LOST:
            assert (record.status, record.prize) == ("lost", 0)
        elif label == PENDING:
            assert (record.status, record.prize) == ("pending", None)
        else:
            assert (record.status, record.tier) == ("won", label)
            assert record.prize > 0


@pytest.mark.parametrize("seed_value", [1, 2, 3, 4, 5])
def test_20件の購入が出るはずの結果になる(db_path, seed_value):
    seed(db_path, 10, seed_value=seed_value)
    purchases = seed_purchases(db_path)
    assert_results_match(db_path, purchases)


def test_当せん数字がゾロ目でも記録できる(db_path):
    seed(db_path, 10, seed_value=1)
    for lottery, numbers in [(LotteryType.NUMBERS3, [7, 7, 7]), (LotteryType.NUMBERS4, [1, 1, 1, 1])]:
        save_draws(lottery, [Draw(round=11, draw_date=datetime.date(2030, 1, 1), numbers=numbers, bonus=[])], db_path)
    seed(db_path, 11, seed_value=1)   # 第11回の賞金を作る
    purchases = seed_purchases(db_path)
    assert_results_match(db_path, purchases)


def test_本物のDBには保存しない():
    with patch("scripts.seed_sample_purchases.make_sample_purchases") as mock_make:
        with pytest.raises(SystemExit, match="本物の DB"):
            seed_purchases(DEFAULT_DB_PATH)
    mock_make.assert_not_called()
