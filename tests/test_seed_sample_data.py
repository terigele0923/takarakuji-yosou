import datetime
import importlib
import os
import random
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app import config
from app.config import DEFAULT_DB_PATH
from app.schemas.lottery import Draw, LotteryType
from app.services.lottery_data import load_draws, validate_draw
from scripts.seed_sample_data import make_sample_draws, make_sample_prizes, seed

CREATE_TABLES_SQL = Path(__file__).resolve().parent.parent / "scripts" / "create_tables.sql"


@pytest.fixture
def db_path(tmp_path):
    """一時フォルダにテスト専用の DB を作り、表を作る"""
    path = tmp_path / "sample.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(CREATE_TABLES_SQL.read_text(encoding="utf-8"))
    return path


@pytest.mark.parametrize("lottery", list(LotteryType))
def test_作ったデータはすべてルールに合っている(lottery):
    end_date = datetime.date(2026, 10, 30)
    draws = make_sample_draws(lottery, 500, random.Random(1), end_date)

    assert [draw.round for draw in draws] == list(range(1, 501))
    assert draws[-1].draw_date == end_date
    assert all(a.draw_date < b.draw_date for a, b in zip(draws, draws[1:]))
    for draw in draws:
        validate_draw(lottery, draw)


def test_同じ乱数の種なら同じデータになる():
    end_date = datetime.date(2026, 10, 30)
    first = make_sample_draws(LotteryType.LOTO6, 10, random.Random(42), end_date)
    second = make_sample_draws(LotteryType.LOTO6, 10, random.Random(42), end_date)
    assert first == second


def test_5種類それぞれ指定した回数分を保存する(db_path):
    result = seed(db_path, 500, seed_value=1)
    assert result == {lottery: 500 for lottery in LotteryType}
    for lottery in LotteryType:
        assert len(load_draws(lottery, db_path)) == 500


def test_2回実行しても重複して保存しない(db_path):
    seed(db_path, 5, seed_value=1)
    assert seed(db_path, 5, seed_value=2) == {lottery: 0 for lottery in LotteryType}


def test_本物のDBには保存しない():
    with pytest.raises(SystemExit, match="本物の DB"):
        seed(DEFAULT_DB_PATH, 5)


def test_環境変数でDBの場所を変えられる():
    try:
        with patch.dict(os.environ, {"LOTTERY_DB_PATH": "data/sample.db"}):
            importlib.reload(config)
            assert config.DB_PATH == config.BASE_DIR / "data" / "sample.db"
        with patch.dict(os.environ, {}, clear=True):
            importlib.reload(config)
            assert config.DB_PATH == config.DEFAULT_DB_PATH
    finally:
        importlib.reload(config)


def test_仮の賞金も保存し件数を増やすと増えた回だけ保存する(db_path):
    seed(db_path, 5, seed_value=1)
    assert seed(db_path, 6, seed_value=2) == {lottery: 1 for lottery in LotteryType}
    with sqlite3.connect(db_path) as conn:
        rounds = conn.execute(
            "SELECT COUNT(DISTINCT round) FROM prizes WHERE lottery = 'loto6'"
        ).fetchone()[0]
        tiers = conn.execute(
            "SELECT tier FROM prizes WHERE lottery = 'loto6' AND round = 6 ORDER BY tier"
        ).fetchall()
    assert rounds == 6
    assert [tier for (tier,) in tiers] == ["1等", "2等", "3等", "4等", "5等"]


def test_ナンバーズの仮の賞金は当せん数字の並べ方で決まる():
    def numbers3(numbers):
        return make_sample_prizes(LotteryType.NUMBERS3, Draw(
            round=1, draw_date=datetime.date(2026, 1, 1), numbers=numbers, bonus=[],
        ))

    assert numbers3([1, 2, 3]) == {
        "ストレート": 90_000, "ボックス": 15_000,
        "セット・ストレート": 52_500, "セット・ボックス": 7_500, "ミニ": 9_000,
    }
    assert numbers3([0, 8, 8])["ボックス"] == 30_000
    assert numbers3([7, 7, 7]) == {"ストレート": 90_000, "ミニ": 9_000}
