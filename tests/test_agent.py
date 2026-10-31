import datetime
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import app
from app.schemas.lottery import Draw, LotteryType, PlayType
from app.schemas.purchase import PurchaseRequest
from app.services import agent_service
from app.services.lottery_data import (
    load_average_prizes,
    load_draw,
    load_draws,
    save_draws,
    save_prizes,
)
from app.services.purchase_service import list_purchases, save_purchase

client = TestClient(app)

CREATE_TABLES_SQL = Path(__file__).resolve().parent.parent / "scripts" / "create_tables.sql"


@pytest.fixture
def db_path(tmp_path):
    """テスト専用の DB にロト6の抽選結果3回分と仮の賞金を入れ、道具がその DB を使うようにする"""
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(CREATE_TABLES_SQL.read_text(encoding="utf-8"))
    save_draws(LotteryType.LOTO6, [
        Draw(round=1, draw_date=datetime.date(2026, 1, 1), numbers=[1, 2, 3, 4, 5, 6], bonus=[7]),
        Draw(round=2, draw_date=datetime.date(2026, 1, 4), numbers=[1, 8, 9, 10, 11, 12], bonus=[13]),
        Draw(round=3, draw_date=datetime.date(2026, 1, 8), numbers=[1, 5, 12, 19, 30, 41], bonus=[22]),
    ], path)
    save_prizes(LotteryType.LOTO6, {3: {
        "1等": 200_000_000, "2等": 10_000_000, "3等": 300_000, "4等": 6_800, "5等": 1_000,
    }}, path)

    with patch.object(agent_service, "load_draws", lambda lottery: load_draws(lottery, path)), \
         patch.object(agent_service, "load_draw", lambda lottery, round: load_draw(lottery, round, path)), \
         patch.object(agent_service, "load_average_prizes", lambda lottery: load_average_prizes(lottery, path)), \
         patch.object(agent_service, "list_purchases", lambda: list_purchases(path)):
        yield path


def call(tool, **args):
    return tool.invoke(args)


def test_道具の一覧():
    assert [tool.name for tool in agent_service.TOOLS] == [
        "lottery_rules", "recent_draws", "draw_result", "number_stats",
        "historical_pattern_analysis", "winning_odds", "purchase_summary", "cost_simulation",
    ]


def test_ルールの道具():
    rules = json.loads(call(agent_service.lottery_rules))
    loto7 = next(item for item in rules if item["lottery"] == "loto7")
    assert loto7["price"] == 300
    assert loto7["bonus_count"] == 2
    assert loto7["tiers"][0] == {"tier": "1等", "matches": 7, "bonus": None}
    numbers3 = next(item for item in rules if item["lottery"] == "numbers3")
    assert numbers3["play_types"] == ["straight", "box", "set", "mini"]


def test_最近の結果の道具は新しい順で件数を絞る(db_path):
    draws = json.loads(call(agent_service.recent_draws, lottery="loto6", count=2))
    assert [draw["round"] for draw in draws] == [3, 2]


def test_特定の回の結果の道具(db_path):
    result = json.loads(call(agent_service.draw_result, lottery="loto6", round=3))
    assert result["numbers"] == [1, 5, 12, 19, 30, 41]
    assert "まだありません" in call(agent_service.draw_result, lottery="loto6", round=99)


def test_集計の道具(db_path):
    result = json.loads(call(agent_service.number_stats, lottery="loto6", top=3))
    assert result["total_draws"] == 3
    assert result["positions"][0]["most_frequent"][0] == {"number": 1, "count": 3, "gap": 0}
    assert "まだありません" in call(agent_service.number_stats, lottery="loto7")


def test_全期間の番号頻度とペア割合の道具(db_path):
    result = json.loads(call(agent_service.historical_pattern_analysis, lottery="loto6"))

    assert result["total_draws"] == 3
    assert result["frequency_matrices"][0]["title"] == "本数字の出現回数"
    assert len(result["cooccurrence_matrices"][0]["counts"]) == 43
    assert "次回の当選確率ではない" in result["note"]


def test_当せん確率の道具():
    odds = json.loads(call(agent_service.winning_odds, lottery="loto6", numbers=[1, 2, 3, 4, 5, 6]))
    assert odds[0]["tier"] == "1等"
    assert odds[0]["odds_text"] == "1/6,096,454"


def test_収支の道具(db_path):
    save_purchase(PurchaseRequest(
        lottery=LotteryType.LOTO6, round=3, numbers=[1, 5, 12, 2, 3, 4], play_type=PlayType.NORMAL,
    ), db_path)
    result = json.loads(call(agent_service.purchase_summary))
    assert result["summary"]["count"] == 1
    assert result["summary"]["spent"] == 200
    assert result["recent_purchases"][0]["numbers"] == [1, 2, 3, 4, 5, 12]


def test_試算の道具(db_path):
    result = json.loads(call(agent_service.cost_simulation, lottery="loto6", tickets_per_draw=2, draws=104))
    assert result["tickets"] == 208
    assert result["cost"] == 41_600
    assert result["expected_profit"] == result["expected_return"] - 41_600
    assert 0 < result["return_rate"] < 1
    assert "計算できません" in call(agent_service.cost_simulation, lottery="loto7", tickets_per_draw=1, draws=1)


def test_DBが準備されていなければ道具はその旨を返す():
    with patch.object(agent_service, "load_draws", side_effect=FileNotFoundError):
        assert call(agent_service.recent_draws, lottery="loto6") == "抽選結果のデータベースが準備されていません。"


def test_エージェントは道具と会話の記憶を持つ():
    agent_service.get_agent.cache_clear()
    try:
        with patch.object(agent_service, "create_agent") as mock_create, \
             patch.object(agent_service, "ChatOpenAI"):
            prompt = agent_service.load_analysis_prompt()
            agent_service.get_agent(prompt)
            agent_service.get_agent(prompt)
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] == agent_service.TOOLS
        assert kwargs["system_prompt"] == f"{agent_service.SYSTEM_PROMPT}\n\n{prompt}"
        assert kwargs["checkpointer"] is not None
    finally:
        agent_service.get_agent.cache_clear()


def test_質問すると最後の返答を返し会話の番号を渡す():
    agent = MagicMock()
    agent.invoke.return_value = {"messages": [AIMessage(content="途中"), AIMessage(content="答え")]}
    with patch.object(agent_service, "load_analysis_prompt", return_value="分析ガイド"), \
         patch.object(agent_service, "get_agent", return_value=agent) as get_agent:
        assert agent_service.ask("ロト6の最近の結果は？", "thread-1") == "答え"
    get_agent.assert_called_once_with("分析ガイド")
    args = agent.invoke.call_args.args
    assert args[0] == {"messages": [{"role": "user", "content": "ロト6の最近の結果は？"}]}
    assert args[1] == {"configurable": {"thread_id": "thread-1"}}


def test_相談のAPI():
    with patch.object(agent_service, "ask", return_value="答え") as mock_ask:
        response = client.post("/api/agent", json={"message": "質問", "thread_id": "abc"})
    assert response.status_code == 200
    assert response.json() == {"answer": "答え"}
    mock_ask.assert_called_once_with("質問", "abc")


@pytest.mark.parametrize(
    "body",
    [
        {"message": "   ", "thread_id": "abc"},
        {"message": "あ" * 1001, "thread_id": "abc"},
        {"message": "質問", "thread_id": ""},
        {"message": "質問"},
    ],
)
def test_相談のAPIで入力が正しくなければ422(body):
    with patch.object(agent_service, "ask") as mock_ask:
        response = client.post("/api/agent", json=body)
    assert response.status_code == 422
    mock_ask.assert_not_called()


def test_相談のAPIでAIに接続できなければ503():
    error = openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
    with patch.object(agent_service, "ask", side_effect=error):
        response = client.post("/api/agent", json={"message": "質問", "thread_id": "abc"})
    assert response.status_code == 503
