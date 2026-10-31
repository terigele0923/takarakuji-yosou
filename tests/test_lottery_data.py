import datetime
import sqlite3
from pathlib import Path

import pytest

from app.schemas.lottery import Draw, LotteryType
from app.services.lottery_data import load_draws, save_draws

CREATE_TABLES_SQL = Path(__file__).resolve().parent.parent / "scripts" / "create_tables.sql"


@pytest.fixture
def db_path(tmp_path):
    """一時フォルダにテスト専用の DB を作り、表を作る"""
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(CREATE_TABLES_SQL.read_text(encoding="utf-8"))
    return path


def make_draw(round, numbers, bonus, draw_date=datetime.date(2026, 1, 5)):
    return Draw(round=round, draw_date=draw_date, numbers=numbers, bonus=bonus)


def test_ロト6を保存して回の順に読み込む(db_path):
    saved = save_draws(LotteryType.LOTO6, [
        make_draw(2, [3, 11, 20, 28, 35, 43], [7], datetime.date(2026, 1, 8)),
        make_draw(1, [1, 5, 12, 19, 30, 41], [22]),
    ], db_path)
    assert saved == 2
    draws = load_draws(LotteryType.LOTO6, db_path)
    assert [draw.round for draw in draws] == [1, 2]
    assert draws[0] == make_draw(1, [1, 5, 12, 19, 30, 41], [22])
    assert draws[1].draw_date == datetime.date(2026, 1, 8)


@pytest.mark.parametrize(
    ("lottery", "numbers", "bonus"),
    [
        (LotteryType.NUMBERS3, [0, 8, 8], []),
        (LotteryType.NUMBERS4, [9, 0, 0, 1], []),
        (LotteryType.MINILOTO, [1, 8, 15, 22, 31], [4]),
        (LotteryType.LOTO6, [1, 5, 12, 19, 30, 43], [22]),
        (LotteryType.LOTO7, [1, 2, 3, 4, 5, 6, 37], [10, 20]),
    ],
)
def test_5種類とも保存して読み込める(db_path, lottery, numbers, bonus):
    assert save_draws(lottery, [make_draw(1, numbers, bonus)], db_path) == 1
    assert load_draws(lottery, db_path) == [make_draw(1, numbers, bonus)]


def test_種類ごとに分けて読み込む(db_path):
    save_draws(LotteryType.LOTO6, [make_draw(1, [1, 5, 12, 19, 30, 41], [22])], db_path)
    save_draws(LotteryType.NUMBERS3, [make_draw(1, [0, 8, 4], [])], db_path)
    assert load_draws(LotteryType.LOTO6, db_path)[0].numbers == [1, 5, 12, 19, 30, 41]
    assert load_draws(LotteryType.NUMBERS3, db_path)[0].numbers == [0, 8, 4]
    assert load_draws(LotteryType.LOTO7, db_path) == []


def test_保存済みの回は飛ばして新しい回だけ保存する(db_path):
    save_draws(LotteryType.LOTO6, [make_draw(1, [1, 5, 12, 19, 30, 41], [22])], db_path)
    saved = save_draws(LotteryType.LOTO6, [
        make_draw(1, [2, 6, 13, 20, 31, 42], [23]),
        make_draw(2, [3, 11, 20, 28, 35, 43], [7]),
    ], db_path)
    assert saved == 1
    draws = load_draws(LotteryType.LOTO6, db_path)
    assert [draw.round for draw in draws] == [1, 2]
    assert draws[0].numbers == [1, 5, 12, 19, 30, 41]


@pytest.mark.parametrize(
    ("lottery", "numbers", "bonus", "message"),
    [
        (LotteryType.LOTO6, [1, 5, 12, 19, 30], [22], "本数字は 6 個"),
        (LotteryType.LOTO7, [1, 2, 3, 4, 5, 6, 7], [10], "ボーナス数字は 2 個"),
        (LotteryType.LOTO6, [1, 5, 12, 19, 30, 44], [22], "1〜43 の範囲"),
        (LotteryType.LOTO6, [0, 5, 12, 19, 30, 41], [22], "1〜43 の範囲"),
        (LotteryType.LOTO7, [1, 2, 3, 4, 5, 6, 38], [10, 20], "1〜37 の範囲"),
        (LotteryType.MINILOTO, [1, 8, 15, 22, 32], [4], "1〜31 の範囲"),
        (LotteryType.NUMBERS3, [0, 8, 10], [], "0〜9 の範囲"),
        (LotteryType.LOTO6, [1, 1, 12, 19, 30, 41], [22], "重複"),
        (LotteryType.LOTO6, [1, 5, 12, 19, 30, 41], [41], "重複"),
    ],
)
def test_ルールに合わない結果は保存しない(db_path, lottery, numbers, bonus, message):
    with pytest.raises(ValueError, match=message) as error:
        save_draws(lottery, [make_draw(3, numbers, bonus)], db_path)
    assert "第3回" in str(error.value)
    assert load_draws(lottery, db_path) == []


def test_1件でもルールに合わなければ1件も保存しない(db_path):
    with pytest.raises(ValueError):
        save_draws(LotteryType.LOTO6, [
            make_draw(1, [1, 5, 12, 19, 30, 41], [22]),
            make_draw(2, [1, 5, 12, 19, 30, 99], [22]),
        ], db_path)
    assert load_draws(LotteryType.LOTO6, db_path) == []


def test_DBのファイルがないとエラーになる(tmp_path):
    with pytest.raises(FileNotFoundError, match="DB のファイルがありません"):
        load_draws(LotteryType.LOTO6, tmp_path / "none.db")
