import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from app.schemas.lottery import LotteryType
from scripts.import_mizuho_data import apply_records, compare_database, parse_mizuho_csv


MINILOTO_CSV = """A51
第0600回ミニロト,数字選択式全国自治宝くじ,平成23年2月8日,東京 宝くじドリーム館
支払期間,平成23年2月9日から平成24年2月8日まで
本数字,01,02,03,04,22,ボーナス数字,13
１等,10口,26415600円
２等,84口,225900円
３等,4155口,7900円
４等,73684口,1100円
販売実績額,893477600円
"""

LOTO7_CSV = """A53
第0001回ロト７,数字選択式全国自治宝くじ,平成25年4月5日,東京 宝くじドリーム館
支払期間,平成25年4月6日から平成26年4月5日まで
本数字,07,10,12,17,23,28,34,ボーナス数字,03,15
１等,1口,301716500円
２等,24口,4144600円
３等,168口,828900円
４等,8254口,9800円
５等,115022口,1700円
６等,189593口,900円
"""

NUMBERS_CSV = """A50
第6801回ナンバーズ,数字選択式全国自治宝くじ,令和7年8月28日,東京 宝くじドリーム館
支払期間,令和7年8月29日から令和8年8月28日まで
ナンバーズ３抽せん数字,186
ストレート,186,43口,91300円
ボックス,509口,15200円
セット（ストレート）,190口,53200円
セット（ボックス）,1275口,7600円
ミニ,368口,9100円
ナンバーズ４抽せん数字,0774
ストレート,0774,149口,425500円
ボックス,173口,35400円
セット（ストレート）,42口,230400円
セット（ボックス）,689口,17700円
"""


def test_parse_loto_csv_results_and_prizes() -> None:
    records = parse_mizuho_csv("miniloto", MINILOTO_CSV)

    assert len(records) == 1
    record = records[0]
    assert record.lottery == LotteryType.MINILOTO
    assert record.draw.round == 600
    assert record.draw.draw_date == dt.date(2011, 2, 8)
    assert record.draw.numbers == [1, 2, 3, 4, 22]
    assert record.draw.bonus == [13]
    assert record.prizes == {"1等": 26_415_600, "2等": 225_900, "3等": 7_900, "4等": 1_100}


def test_parse_numbers_csv_preserves_digit_positions_and_maps_tiers() -> None:
    records = parse_mizuho_csv("numbers", NUMBERS_CSV)

    numbers3, numbers4 = records
    assert numbers3.lottery == LotteryType.NUMBERS3
    assert numbers3.draw.numbers == [1, 8, 6]
    assert numbers3.prizes == {
        "ストレート": 91_300,
        "ボックス": 15_200,
        "セット・ストレート": 53_200,
        "セット・ボックス": 7_600,
        "ミニ": 9_100,
    }
    assert numbers4.lottery == LotteryType.NUMBERS4
    assert numbers4.draw.numbers == [0, 7, 7, 4]
    assert numbers4.prizes == {
        "ストレート": 425_500,
        "ボックス": 35_400,
        "セット・ストレート": 230_400,
        "セット・ボックス": 17_700,
    }


def test_parse_loto7_prizes_and_fullwidth_tiers() -> None:
    record = parse_mizuho_csv("loto7", LOTO7_CSV)[0]

    assert record.draw.round == 1
    assert record.draw.draw_date == dt.date(2013, 4, 5)
    assert record.draw.numbers == [7, 10, 12, 17, 23, 28, 34]
    assert record.draw.bonus == [3, 15]
    assert record.prizes["1等"] == 301_716_500
    assert record.prizes["6等"] == 900


def test_skip_prizes_without_a_winner_amount() -> None:
    csv_text = MINILOTO_CSV.replace("１等,10口,26415600円", "１等,該当なし,該当なし")

    record = parse_mizuho_csv("miniloto", csv_text)[0]

    assert "1等" not in record.prizes


def test_reject_invalid_draw_numbers() -> None:
    csv_text = MINILOTO_CSV.replace("本数字,01,02,03,04,22", "本数字,01,02,03,04")

    with pytest.raises(ValueError, match="本数字は 5 個"):
        parse_mizuho_csv("miniloto", csv_text)


def test_compare_and_apply_records_with_backup(tmp_path) -> None:
    db_path = tmp_path / "lottery.db"
    schema_path = Path(__file__).resolve().parents[1] / "scripts" / "create_tables.sql"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))

    records = parse_mizuho_csv("miniloto", MINILOTO_CSV)
    summary, conflicts = compare_database(db_path, records)

    assert not conflicts
    assert summary["new_draws"] == 1
    assert summary["new_prizes"] == 4
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM draws").fetchone()[0] == 0

    backup_path = apply_records(db_path, records)
    assert backup_path.is_file()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM draws").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM prizes").fetchone()[0] == 4

    repeated_summary, repeated_conflicts = compare_database(db_path, records)
    assert not repeated_conflicts
    assert repeated_summary["existing_draws"] == 1
    assert repeated_summary["existing_prizes"] == 4
