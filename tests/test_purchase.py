import datetime
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.lottery import Draw, LotteryType, PlayType
from app.schemas.purchase import PurchaseRequest, PurchaseStatus
from app.services.lottery_data import save_draws, save_prizes
from app.services.purchase_service import check_results, list_purchases, save_purchase

client = TestClient(app)

CREATE_TABLES_SQL = Path(__file__).resolve().parent.parent / "scripts" / "create_tables.sql"


@pytest.fixture
def db_path(tmp_path):
    """一時フォルダにテスト専用の DB を作り、表を作る"""
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(CREATE_TABLES_SQL.read_text(encoding="utf-8"))
    return path


def saved_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM purchases ORDER BY id")]


def use_db(db_path):
    """API から呼ばれる save_purchase の保存先を、テスト用の DB にする"""
    return patch(
        "app.services.purchase_service.save_purchase",
        side_effect=lambda request: save_purchase(request, db_path),
    )


def request(lottery, numbers, play_type, round=3):
    return PurchaseRequest(lottery=lottery, round=round, numbers=numbers, play_type=play_type)


def test_表を作るSQLは2回実行してもエラーにならない(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(CREATE_TABLES_SQL.read_text(encoding="utf-8"))
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"draws", "prizes", "purchases"} <= tables


def test_ロト6の購入を小さい順の番号で記録する(db_path):
    result = save_purchase(request(LotteryType.LOTO6, [43, 1, 20, 12, 5, 30], PlayType.NORMAL), db_path)
    assert result.id == 1
    assert result.numbers == [1, 5, 12, 20, 30, 43]
    assert result.price == 200

    row = saved_rows(db_path)[0]
    assert row["lottery"] == "loto6"
    assert row["round"] == 3
    assert row["numbers"] == "1,5,12,20,30,43"
    assert row["play_type"] == "normal"
    assert row["price"] == 200
    assert row["purchased_at"]
    assert row["tier"] is None and row["prize"] is None


def test_ロト7は1口300円(db_path):
    result = save_purchase(request(LotteryType.LOTO7, [1, 2, 3, 4, 5, 6, 7], PlayType.NORMAL), db_path)
    assert result.price == 300


@pytest.mark.parametrize("play_type", [PlayType.STRAIGHT, PlayType.BOX, PlayType.SET])
def test_ナンバーズ4は申込タイプを記録する(db_path, play_type):
    result = save_purchase(request(LotteryType.NUMBERS4, [4, 3, 6, 1], play_type), db_path)
    row = saved_rows(db_path)[0]
    assert result.numbers == [4, 3, 6, 1]
    assert row["numbers"] == "4,3,6,1"
    assert row["play_type"] == play_type.value
    assert row["price"] == 200


def test_ミニは下2桁を記録する(db_path):
    result = save_purchase(request(LotteryType.NUMBERS3, [1, 2, 3], PlayType.MINI), db_path)
    assert result.numbers == [2, 3]
    assert saved_rows(db_path)[0]["numbers"] == "2,3"


@pytest.mark.parametrize(
    ("lottery", "numbers", "play_type"),
    [
        (LotteryType.NUMBERS3, [7, 7, 7], PlayType.BOX),       # ゾロ目のボックス
        (LotteryType.NUMBERS4, [1, 1, 1, 1], PlayType.SET),    # ゾロ目のセット
        (LotteryType.NUMBERS4, [1, 2, 3, 4], PlayType.MINI),   # ミニはナンバーズ3のみ
        (LotteryType.LOTO6, [1, 2, 3, 4, 5, 6], PlayType.STRAIGHT),
        (LotteryType.NUMBERS3, [1, 2, 3], PlayType.NORMAL),
    ],
)
def test_選べない申込タイプは記録しない(db_path, lottery, numbers, play_type):
    with pytest.raises(ValueError, match="その申込タイプは選べません"):
        save_purchase(request(lottery, numbers, play_type), db_path)
    assert saved_rows(db_path) == []


def test_ルールに合わない番号は記録しない(db_path):
    with pytest.raises(ValueError, match="1〜43 の範囲"):
        save_purchase(request(LotteryType.LOTO6, [1, 2, 3, 4, 5, 44], PlayType.NORMAL), db_path)
    assert saved_rows(db_path) == []


def test_購入のAPIで記録できる(db_path):
    with use_db(db_path):
        response = client.post("/api/purchases", json={
            "lottery": "numbers3", "round": 501, "numbers": [0, 8, 8], "play_type": "box",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["round"] == 501
    assert body["numbers"] == [0, 8, 8]
    assert body["play_type"] == "box"
    assert body["price"] == 200
    assert saved_rows(db_path)[0]["play_type"] == "box"


def test_購入のAPIで選べない申込タイプは422(db_path):
    with use_db(db_path):
        response = client.post("/api/purchases", json={
            "lottery": "numbers3", "round": 501, "numbers": [7, 7, 7], "play_type": "box",
        })
    assert response.status_code == 422
    assert "その申込タイプは選べません" in response.json()["detail"]


def test_購入のAPIで回が0以下は422():
    response = client.post("/api/purchases", json={
        "lottery": "loto6", "round": 0, "numbers": [1, 2, 3, 4, 5, 6], "play_type": "normal",
    })
    assert response.status_code == 422


def test_購入のAPIで表がなければ503(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with use_db(empty):
        response = client.post("/api/purchases", json={
            "lottery": "loto6", "round": 3, "numbers": [1, 2, 3, 4, 5, 6], "play_type": "normal",
        })
    assert response.status_code == 503
    assert response.json() == {"detail": "抽選結果のデータベースが準備されていません"}


# ---- 結果の確認と収支 ----

def add_loto6_result(db_path, round=3, with_prizes=True):
    """ロト6の抽選結果（1,5,12,19,30,41 ボーナス22）と仮の賞金を保存する"""
    save_draws(LotteryType.LOTO6, [Draw(
        round=round, draw_date=datetime.date(2026, 1, 8),
        numbers=[1, 5, 12, 19, 30, 41], bonus=[22],
    )], db_path)
    if with_prizes:
        save_prizes(LotteryType.LOTO6, {round: {
            "1等": 200_000_000, "2等": 10_000_000, "3等": 300_000, "4等": 6_800, "5等": 1_000,
        }}, db_path)


def test_結果がまだの回は未確認のまま(db_path):
    save_purchase(request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL), db_path)
    result = check_results(db_path)
    assert result.purchases[0].status == "pending"
    assert result.purchases[0].prize is None
    assert result.purchases[0].winning_numbers is None
    assert result.purchases[0].bonus_numbers is None
    assert result.summary.pending_count == 1
    assert result.checked_count == 0


def test_当たりと外れを記録して収支を計算する(db_path):
    add_loto6_result(db_path)
    save_purchase(request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL), db_path)    # 5等
    save_purchase(request(LotteryType.LOTO6, [1, 2, 3, 4, 6, 7], PlayType.NORMAL), db_path)     # 外れ
    save_purchase(request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL, round=4), db_path)  # 未確認

    result = check_results(db_path)
    by_id = {record.id: record for record in result.purchases}
    assert [record.id for record in result.purchases] == [3, 2, 1]
    assert (by_id[1].status, by_id[1].tier, by_id[1].prize) == ("won", "5等", 1_000)
    assert by_id[1].winning_numbers == [1, 5, 12, 19, 30, 41]
    assert by_id[1].bonus_numbers == [22]
    assert (by_id[2].status, by_id[2].tier, by_id[2].prize) == ("lost", None, 0)
    assert (by_id[3].status, by_id[3].prize) == ("pending", None)

    summary = result.summary
    assert summary.count == 3
    assert summary.spent == 600
    assert summary.won == 1_000
    assert summary.profit == 400
    assert summary.pending_count == 1
    assert result.checked_count == 2

    rows = {row["id"]: row for row in saved_rows(db_path)}
    assert (rows[1]["tier"], rows[1]["prize"]) == ("5等", 1_000)
    assert (rows[2]["tier"], rows[2]["prize"]) == (None, 0)


def test_抽選日と回と結果で収支を絞り込み小計する(db_path):
    add_loto6_result(db_path, round=3)
    save_draws(
        LotteryType.LOTO6,
        [
            Draw(
                round=4,
                draw_date=datetime.date(2026, 2, 1),
                numbers=[2, 6, 13, 20, 31, 42],
                bonus=[23],
            )
        ],
        db_path,
    )
    save_purchase(
        request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL, round=3),
        db_path,
    )
    save_purchase(
        request(LotteryType.LOTO6, [1, 2, 3, 4, 6, 7], PlayType.NORMAL, round=4),
        db_path,
    )
    save_purchase(
        request(LotteryType.LOTO6, [1, 2, 3, 4, 6, 7], PlayType.NORMAL, round=5),
        db_path,
    )
    check_results(db_path)

    won = list_purchases(
        db_path,
        date_from=datetime.date(2026, 1, 8),
        date_to=datetime.date(2026, 1, 8),
        status=PurchaseStatus.WON,
    )
    round_four = list_purchases(db_path, round_number=4)
    pending = list_purchases(db_path, status=PurchaseStatus.PENDING)

    assert [record.round for record in won.purchases] == [3]
    assert won.purchases[0].draw_date == datetime.date(2026, 1, 8)
    assert (won.summary.count, won.summary.spent, won.summary.won) == (1, 200, 1_000)
    assert [record.round for record in round_four.purchases] == [4]
    assert [record.round for record in pending.purchases] == [5]


def test_収支絞り込みの開始日が終了日より後ならエラー(db_path):
    with pytest.raises(ValueError, match="開始日"):
        list_purchases(
            db_path,
            date_from=datetime.date(2026, 2, 1),
            date_to=datetime.date(2026, 1, 1),
        )


def test_賞金がまだなければ賞金未登録になりあとで確定する(db_path):
    add_loto6_result(db_path, with_prizes=False)
    save_purchase(request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL), db_path)
    record = check_results(db_path).purchases[0]
    assert (record.status, record.tier, record.prize) == ("prize_unknown", "5等", None)

    save_prizes(LotteryType.LOTO6, {3: {"5等": 1_000}}, db_path)
    record = check_results(db_path).purchases[0]
    assert (record.status, record.tier, record.prize) == ("won", "5等", 1_000)


def test_ナンバーズのセットとミニを照らし合わせる(db_path):
    save_draws(LotteryType.NUMBERS3, [Draw(
        round=3, draw_date=datetime.date(2026, 1, 8), numbers=[0, 8, 4], bonus=[],
    )], db_path)
    save_prizes(LotteryType.NUMBERS3, {3: {"セット・ボックス": 7_500, "ミニ": 9_000}}, db_path)
    save_purchase(request(LotteryType.NUMBERS3, [4, 8, 0], PlayType.SET), db_path)
    save_purchase(request(LotteryType.NUMBERS3, [1, 8, 4], PlayType.MINI), db_path)

    by_id = {record.id: record for record in check_results(db_path).purchases}
    assert (by_id[1].tier, by_id[1].prize) == ("セット・ボックス", 7_500)
    assert (by_id[2].tier, by_id[2].prize) == ("ミニ", 9_000)


def test_確定した購入は確認し直さない(db_path):
    add_loto6_result(db_path)
    save_purchase(request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL), db_path)
    check_results(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE prizes SET amount = 9999 WHERE tier = '5等'")
    assert check_results(db_path).purchases[0].prize == 1_000


def test_期待される戻りは当せん確率と平均の賞金から計算する(db_path):
    add_loto6_result(db_path)
    save_purchase(request(LotteryType.LOTO6, [1, 2, 3, 4, 6, 7], PlayType.NORMAL), db_path)
    record = list_purchases(db_path).purchases[0]
    expected = (
        200_000_000 / 6_096_454 + 10_000_000 * 6 / 6_096_454 + 300_000 * 216 / 6_096_454
        + 6_800 * 9_990 / 6_096_454 + 1_000 * 155_400 / 6_096_454
    )
    assert record.expected_return == pytest.approx(expected)
    assert list_purchases(db_path).summary.expected_is_partial is False


def test_賞金のデータがなければ期待される戻りは出さない(db_path):
    save_purchase(request(LotteryType.LOTO6, [1, 2, 3, 4, 6, 7], PlayType.NORMAL), db_path)
    result = list_purchases(db_path)
    assert result.purchases[0].expected_return is None
    assert result.summary.expected_return == 0
    assert result.summary.expected_is_partial is True


def test_収支のAPI(db_path):
    add_loto6_result(db_path)
    save_purchase(request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL), db_path)
    with patch("app.services.purchase_service.list_purchases",
               side_effect=lambda: list_purchases(db_path)):
        response = client.get("/api/purchases")
    assert response.status_code == 200
    assert response.json()["purchases"][0]["status"] == "pending"
    assert response.json()["purchases"][0]["name"] == "ロト6"

    with patch("app.services.purchase_service.check_results",
               side_effect=lambda: check_results(db_path)):
        response = client.post("/api/purchases/check")
    assert response.status_code == 200
    assert response.json()["purchases"][0]["status"] == "won"
    assert response.json()["summary"]["profit"] == 800
    assert response.json()["checked_count"] == 1


def test_収支APIへ絞り込み条件を渡す(db_path):
    add_loto6_result(db_path)
    save_purchase(
        request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL),
        db_path,
    )
    check_results(db_path)
    with patch(
        "app.services.purchase_service.list_purchases",
        side_effect=lambda **filters: list_purchases(db_path, **filters),
    ):
        response = client.get(
            "/api/purchases?date_from=2026-01-08&date_to=2026-01-08"
            "&round_number=3&status=won"
        )
    assert response.status_code == 200
    assert response.json()["summary"]["count"] == 1
    assert response.json()["purchases"][0]["draw_date"] == "2026-01-08"


def test_収支APIの期間が逆なら422():
    response = client.get(
        "/api/purchases?date_from=2026-02-01&date_to=2026-01-01"
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "開始日は終了日以前にしてください"


def test_結果確認を繰り返した場合は新しい情報0件を返す(db_path):
    add_loto6_result(db_path)
    save_purchase(request(LotteryType.LOTO6, [1, 5, 12, 2, 3, 4], PlayType.NORMAL), db_path)
    assert check_results(db_path).checked_count == 1
    assert check_results(db_path).checked_count == 0


def test_収支のAPIで表がなければ503(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with patch("app.services.purchase_service.list_purchases",
               side_effect=lambda: list_purchases(empty)):
        response = client.get("/api/purchases")
    assert response.status_code == 503
