import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.lottery_update_service import (
    LotteryDataConflictError,
    import_official_bundle,
    update_latest_draws,
)

CREATE_TABLES_SQL = Path(__file__).resolve().parent.parent / "scripts" / "create_tables.sql"
MINILOTO_CSV = """A51
第1411回ミニロト,数字選択式全国自治宝くじ,令和8年10月27日,東京 宝くじドリーム館
本数字,02,08,14,20,30,ボーナス数字,04
１等,1口,1234567円
"""


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(CREATE_TABLES_SQL.read_text(encoding="utf-8"))
    return path


def make_bundle(csv_text=MINILOTO_CSV):
    return {
        "source": "Mizuho Bank official per-draw CSVs",
        "files": [{"family": "miniloto", "text": csv_text}],
    }


def test_公式CSVの新しい回をDBに追加してバックアップする(db_path):
    assert import_official_bundle(make_bundle(), db_path) == (1, 1)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT draw_date, numbers, bonus FROM draws WHERE lottery='miniloto' AND round=1411"
        ).fetchone() == ("2026-10-27", "2,8,14,20,30", "4")
        assert connection.execute(
            "SELECT amount FROM prizes WHERE lottery='miniloto' AND round=1411 AND tier='1等'"
        ).fetchone() == (1_234_567,)
    assert list(db_path.parent.glob("test.backup-*.db"))


def test_登録済みのJSONを再読込しても重複追加しない(db_path):
    assert import_official_bundle(make_bundle(), db_path) == (1, 1)
    assert import_official_bundle(make_bundle(), db_path) == (0, 0)


def test_DBと公式CSVに矛盾があれば書き込まずにエラーにする(db_path):
    conflict_csv = MINILOTO_CSV.replace("02,08,14", "03,08,14")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO draws VALUES (?, ?, ?, ?, ?)",
            ("miniloto", 1411, "2026-10-27", "2,8,14,20,30", "4"),
        )

    with pytest.raises(LotteryDataConflictError, match="differs from the official CSV"):
        import_official_bundle(make_bundle(conflict_csv), db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT numbers FROM draws WHERE lottery='miniloto' AND round=1411"
        ).fetchone() == ("2,8,14,20,30",)


def test_不正なJSONはDBに反映しない(db_path):
    with pytest.raises(ValueError, match="Unexpected data source"):
        import_official_bundle({"source": "unknown", "files": []}, db_path)


def test_DBの最終回を起点に各種類の最新CSVをブラウザーへ要求する(db_path):
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO draws VALUES (?, ?, ?, ?, ?)",
            [
                ("numbers3", 7104, "2026-10-30", "1,2,3", ""),
                ("numbers4", 7104, "2026-10-30", "1,2,3,4", ""),
                ("miniloto", 1410, "2026-10-20", "1,2,3,4,5", "6"),
                ("loto6", 2150, "2026-10-29", "1,2,3,4,5,6", "7"),
                ("loto7", 701, "2026-10-30", "1,2,3,4,5,6,7", "8,9"),
            ],
        )

    captured = []

    def fake_browser_fetcher(requests):
        captured.extend(requests)
        return [(family, "dummy") for family, _round, _url in requests]

    with patch("app.services.lottery_update_service.parse_mizuho_csv", return_value=[]):
        assert update_latest_draws(db_path, fake_browser_fetcher) == (0, 0)

    assert [(family, round_number) for family, round_number, _url in captured] == [
        ("numbers", 7104),
        ("miniloto", 1410),
        ("loto6", 2150),
        ("loto7", 701),
    ]
    assert captured[0][2].endswith("/numbers/csv/A1007104.CSV")
