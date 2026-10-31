import datetime
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.lottery import RULES, Draw, LotteryType
from app.services import predict_service
from app.services.bias_prediction_service import (
    BiasPredictionConfig,
    backtest_bias,
    build_bias_model,
    generate_candidates,
)
from app.services.lottery_data import validate_numbers

client = TestClient(app)


def make_loto6_draws(count=80):
    draws = []
    for index in range(count):
        # 直近ほど 1・5・12 が継続して出やすい偏りを持つテストデータ。
        base = [1, 5, 12] if index >= count // 2 else [2, 6, 13]
        rest = [19 + index % 5, 30 + index % 6, 38 + index % 6]
        draws.append(
            Draw(
                round=index + 1,
                draw_date=datetime.date(2025, 1, 1) + datetime.timedelta(days=index * 3),
                numbers=sorted(base + rest),
                bonus=[15],
            )
        )
    return draws


def test_直近と長期の偏りをモデル化する():
    model = build_bias_model(LotteryType.LOTO6, make_loto6_draws())
    rule = RULES[LotteryType.LOTO6]
    assert model.individual_recent[0][1 - rule.min] > model.individual_recent[0][10 - rule.min]
    assert model.individual_long[0][1 - rule.min] > model.individual_long[0][10 - rule.min]


def test_偏り設定は重み合計と正数を検証する():
    with pytest.raises(ValueError, match="重み合計"):
        BiasPredictionConfig(long_weight=0.5)
    with pytest.raises(ValueError, match="半減期"):
        BiasPredictionConfig(recent_half_life=0)


def test_偏り上位からルールに合う異なる候補を生成する():
    model = build_bias_model(LotteryType.LOTO6, make_loto6_draws())
    candidates = generate_candidates(model, 3)
    assert len({candidate.numbers for candidate in candidates}) == 3
    for candidate in candidates:
        validate_numbers(LotteryType.LOTO6, list(candidate.numbers))
    assert candidates == sorted(candidates, key=lambda item: (-item.raw_score, item.numbers))


def test_ナンバーズは桁別偏りを保って候補を生成する():
    draws = [
        Draw(
            round=index + 1,
            draw_date=datetime.date(2026, 1, 1) + datetime.timedelta(days=index),
            numbers=[8, 1, 4] if index > 10 else [2, 9, 0],
            bonus=[],
        )
        for index in range(40)
    ]
    candidates = generate_candidates(build_bias_model(LotteryType.NUMBERS3, draws), 2)
    assert candidates[0].numbers == (8, 1, 4)
    assert sum(a == b for a, b in zip(candidates[0].numbers, candidates[1].numbers)) <= 1


def test_予想結果に偏りスコアとバックテストを含む():
    draws = make_loto6_draws()
    with patch("app.services.predict_service.load_draws", return_value=draws):
        result = predict_service.predict(LotteryType.LOTO6, 2)

    assert result.name == "ロト6"
    assert result.next_round == 81
    assert len(result.sets) == 2
    assert result.sets[0].bias_score >= result.sets[1].bias_score
    assert set(result.sets[0].bias_components) == {"long_term", "recent", "pair"}
    assert "時間加重" in result.prediction_method
    assert result.backtest.evaluated_draws == 40
    assert 0 <= result.backtest.above_random_rate <= 1
    assert result.sets[0].odds[0].odds_text == "1/6,096,454"


def test_同じ履歴からは同じ偏り予想を再現する():
    draws = make_loto6_draws()
    with patch("app.services.predict_service.load_draws", return_value=draws):
        first = predict_service.predict(LotteryType.LOTO6, 2)
        second = predict_service.predict(LotteryType.LOTO6, 2)
    assert [item.numbers for item in first.sets] == [item.numbers for item in second.sets]
    assert first.backtest == second.backtest


def test_バックテストは学習期間より後だけを評価する():
    result = backtest_bias(LotteryType.LOTO6, make_loto6_draws(35))
    assert result.evaluated_draws == 5


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


def test_予想APIが指定組数と偏り検証を返す():
    with patch("app.services.predict_service.load_draws", return_value=make_loto6_draws()):
        response = client.post("/api/predict", json={"lottery": "loto6", "count": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["sets"]) == 2
    assert "bias_score" in body["sets"][0]
    assert body["backtest"]["evaluated_draws"] == 40


def test_予想APIで組数を省くと1組():
    with patch("app.services.predict_service.load_draws", return_value=make_loto6_draws()):
        response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 200
    assert len(response.json()["sets"]) == 1


@pytest.mark.parametrize("count", [0, 11])
def test_予想APIで組数が範囲外なら422(count):
    response = client.post("/api/predict", json={"lottery": "loto6", "count": count})
    assert response.status_code == 422


def test_予想APIでデータがなければ409():
    with patch("app.services.predict_service.load_draws", return_value=[]):
        response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 409
    assert response.json() == {"detail": "ロト6の抽選結果がまだありません"}


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("DB のファイルがありません"), sqlite3.OperationalError("no such table: draws")],
)
def test_予想APIでDBが準備されていなければ503(error):
    with patch("app.services.predict_service.load_draws", side_effect=error):
        response = client.post("/api/predict", json={"lottery": "loto6"})
    assert response.status_code == 503


def test_予想APIで知らない種類は422():
    response = client.post("/api/predict", json={"lottery": "takarakuji"})
    assert response.status_code == 422
