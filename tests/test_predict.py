import datetime
import sqlite3
from unittest.mock import patch

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.lottery import RULES, Draw, LotteryType
from app.schemas.predict import AiPredictedSet, PredictionOutput
from app.services import predict_service
from app.services.stats_service import calculate_stats

client = TestClient(app)

LOTO6_DRAWS = [
    Draw(round=1, draw_date=datetime.date(2026, 1, 5), numbers=[1, 5, 12, 19, 30, 41], bonus=[22]),
    Draw(round=2, draw_date=datetime.date(2026, 1, 8), numbers=[3, 11, 20, 28, 35, 43], bonus=[7]),
]
NUMBERS3_DRAWS = [
    Draw(round=1, draw_date=datetime.date(2026, 1, 5), numbers=[0, 8, 8], bonus=[]),
]


def output(*sets):
    """AI の返答（番号の組の一覧）を作る"""
    return PredictionOutput(sets=[AiPredictedSet(numbers=numbers, reason=f"理由{index}")
                                  for index, numbers in enumerate(sets, start=1)])


@pytest.fixture
def mock_llm():
    """ChatOpenAI をモックに差し替え、AI の返答を順に返すようにする"""
    with patch("app.services.predict_service.ChatOpenAI") as mock_cls:
        invoke = mock_cls.return_value.with_structured_output.return_value.invoke
        yield mock_cls, invoke


@pytest.fixture
def loto6_data():
    with patch("app.services.predict_service.load_draws", return_value=LOTO6_DRAWS):
        yield


def test_ロト6を2組予想すると小さい順の番号と確率が返る(loto6_data, mock_llm):
    _, invoke = mock_llm
    invoke.side_effect = [output([43, 1, 20, 12, 5, 30], [2, 4, 6, 8, 10, 12])]
    result = predict_service.predict(LotteryType.LOTO6, 2)

    assert result.name == "ロト6"
    assert result.price == 200
    assert result.next_round == 3
    assert [item.numbers for item in result.sets] == [[1, 5, 12, 20, 30, 43], [2, 4, 6, 8, 10, 12]]
    assert [item.reason for item in result.sets] == ["理由1", "理由2"]
    assert result.sets[0].odds[0].tier == "1等"
    assert result.sets[0].odds[0].odds_text == "1/6,096,454"
    assert result.total_draws == 2
    assert result.first_date == datetime.date(2026, 1, 5)
    assert result.last_date == datetime.date(2026, 1, 8)
    assert result.last_round == 2


def test_ナンバーズは桁の順のまま返し組ごとの確率が付く(mock_llm):
    _, invoke = mock_llm
    invoke.side_effect = [output([9, 0, 0], [1, 2, 3])]
    with patch("app.services.predict_service.load_draws", return_value=NUMBERS3_DRAWS):
        result = predict_service.predict(LotteryType.NUMBERS3, 2)
    assert [item.numbers for item in result.sets] == [[9, 0, 0], [1, 2, 3]]
    box = {odds.tier: odds for odds in result.sets[0].odds}["ボックス"]
    assert box.probability == pytest.approx(3 / 1_000)
    box = {odds.tier: odds for odds in result.sets[1].odds}["ボックス"]
    assert box.probability == pytest.approx(6 / 1_000)


@pytest.mark.parametrize(
    "bad",
    [
        output([1, 2, 3, 4, 5, 6]),                                  # 組数が足りない
        output([1, 2, 3, 4, 5], [7, 8, 9, 10, 11, 12]),              # 個数が足りない
        output([1, 2, 3, 4, 5, 44], [7, 8, 9, 10, 11, 12]),          # 範囲外
        output([1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1]),              # 同じ組（並びが違うだけ）
    ],
)
def test_ルールに合わない答えならやり直す(loto6_data, mock_llm, bad):
    _, invoke = mock_llm
    invoke.side_effect = [bad, output([1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12])]
    result = predict_service.predict(LotteryType.LOTO6, 2)
    assert len(result.sets) == 2
    assert invoke.call_count == 2


def test_3回ともルールに合わなければエラーになる(loto6_data, mock_llm):
    _, invoke = mock_llm
    invoke.side_effect = [output([1, 1, 2, 3, 4, 5])] * 3
    with pytest.raises(predict_service.InvalidPredictionError):
        predict_service.predict(LotteryType.LOTO6, 1)


def test_データがなければエラーになりAIを呼ばない(mock_llm):
    mock_cls, _ = mock_llm
    with patch("app.services.predict_service.load_draws", return_value=[]):
        with pytest.raises(predict_service.NoDrawDataError, match="ロト7の抽選結果がまだありません"):
            predict_service.predict(LotteryType.LOTO7, 1)
    mock_cls.assert_not_called()


def test_AIに渡す文章にルールと組数と集計結果が入る():
    stats = calculate_stats(LotteryType.LOTO6, LOTO6_DRAWS)
    prompt = predict_service.build_prompt(RULES[LotteryType.LOTO6], stats, 3)
    assert "宝くじ：ロト6" in prompt
    assert "1〜43 から異なる番号を 6 個選ぶ" in prompt
    assert "組数：3組（同じ組を2回選ばない）" in prompt
    assert "集計期間：2026-01-05〜2026-01-08（第2回まで、2回分）" in prompt
    assert "\n1,1,1\n" in prompt
    assert "\n43,1,0" in prompt
    assert "\n2,0,未出\n" in prompt


def test_ナンバーズのAIに渡す文章は桁ごとになる():
    stats = calculate_stats(LotteryType.NUMBERS3, NUMBERS3_DRAWS)
    prompt = predict_service.build_prompt(RULES[LotteryType.NUMBERS3], stats)
    assert "各桁 0〜9 の数字を1つずつ、3桁を選ぶ" in prompt
    assert "[左から1桁目]" in prompt
    assert "[左から3桁目]" in prompt


def test_種類の一覧のAPI():
    response = client.get("/api/lotteries")
    assert response.status_code == 200
    assert response.json() == [
        {"value": "numbers3", "name": "ナンバーズ3"},
        {"value": "numbers4", "name": "ナンバーズ4"},
        {"value": "miniloto", "name": "ミニロト"},
        {"value": "loto6", "name": "ロト6"},
        {"value": "loto7", "name": "ロト7"},
    ]


def test_予想のAPIが組数ぶんの結果を返す(loto6_data, mock_llm):
    _, invoke = mock_llm
    invoke.side_effect = [output([1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12])]
    response = client.post("/api/predict", json={"lottery": "loto6", "count": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["next_round"] == 3
    assert body["price"] == 200
    assert [item["numbers"] for item in body["sets"]] == [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]
    assert body["sets"][0]["odds"][0] == {
        "play_type": "normal",
        "tier": "1等",
        "probability": pytest.approx(1 / 6_096_454),
        "odds_text": "1/6,096,454",
    }


def test_予想のAPIで組数を省くと1組(loto6_data, mock_llm):
    _, invoke = mock_llm
    invoke.side_effect = [output([1, 2, 3, 4, 5, 6])]
    response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 200
    assert len(response.json()["sets"]) == 1


@pytest.mark.parametrize("count", [0, 11])
def test_予想のAPIで組数が範囲外なら422(count):
    response = client.post("/api/predict", json={"lottery": "loto6", "count": count})
    assert response.status_code == 422


def test_予想のAPIでデータがなければ409():
    with patch("app.services.predict_service.load_draws", return_value=[]):
        response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 409
    assert response.json() == {"detail": "ロト6の抽選結果がまだありません"}


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("DB のファイルがありません"), sqlite3.OperationalError("no such table: draws")],
)
def test_予想のAPIでDBが準備されていなければ503(error):
    with patch("app.services.predict_service.load_draws", side_effect=error):
        response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 503
    assert response.json() == {"detail": "抽選結果のデータベースが準備されていません"}


def test_予想のAPIでAIがルールに合う番号を返さなければ502(loto6_data, mock_llm):
    _, invoke = mock_llm
    invoke.side_effect = [output([1])] * 3
    response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 502
    assert "ルールに合う番号を返しませんでした" in response.json()["detail"]


def test_予想のAPIでAIに接続できなければ503(loto6_data, mock_llm):
    _, invoke = mock_llm
    invoke.side_effect = openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
    response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 503
    assert response.json() == {"detail": "AIに接続できませんでした。時間をおいて再度お試しください"}


def test_予想のAPIで知らない種類は422():
    response = client.post("/api/predict", json={"lottery": "takarakuji"})
    assert response.status_code == 422
