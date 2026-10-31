import os
from unittest.mock import patch

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services import chat_service, lottery_update_service

client = TestClient(app)


def test_トップページで画面が返る():
    response = client.get("/")
    assert response.status_code == 200
    assert "宝くじ予想AI" in response.text
    assert 'id="update-data-button"' in response.text
    assert 'id="check-status"' in response.text
    assert '/static/js/app.js?v=20261031-2' in response.text


def test_最新情報の更新件数が返る():
    with patch(
        "app.api.routes.lottery_update_service.update_latest_draws",
        return_value=(2, 8),
    ):
        response = client.post("/api/lottery-data/update")
    assert response.status_code == 200
    assert response.json() == {"added_draws": 2, "added_prizes": 8}


def test_DBとの矛盾は409で返す():
    with patch(
        "app.api.routes.lottery_update_service.update_latest_draws",
        side_effect=lottery_update_service.LotteryDataConflictError("DBとの矛盾"),
    ):
        response = client.post("/api/lottery-data/update")
    assert response.status_code == 409
    assert response.json() == {"detail": "DBとの矛盾"}


def test_公式サイトをブラウザーで取得できない場合は502を返す():
    with patch(
        "app.api.routes.lottery_update_service.update_latest_draws",
        side_effect=lottery_update_service.OfficialSiteError("公式サイトを開けません"),
    ):
        response = client.post("/api/lottery-data/update")
    assert response.status_code == 502
    assert response.json() == {"detail": "公式サイトを開けません"}


def test_CSSとJSが配信される():
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200


def test_質問を送ると回答が返る():
    # 本物の API は呼ばず、返答をモックに差し替える
    with patch("app.services.chat_service.ask", return_value="テスト回答") as mock_ask:
        response = client.post("/api/chat", json={"question": "LangChainとは？"})
    assert response.status_code == 200
    assert response.json() == {"answer": "テスト回答"}
    mock_ask.assert_called_once_with("LangChainとは？")


def test_空白だけの質問はエラーになる():
    with patch("app.services.chat_service.ask") as mock_ask:
        response = client.post("/api/chat", json={"question": "   "})
    assert response.status_code == 422
    mock_ask.assert_not_called()


def test_質問がないとエラーになる():
    response = client.post("/api/chat", json={})
    assert response.status_code == 422


def test_1000文字の質問は受け付ける():
    with patch("app.services.chat_service.ask", return_value="テスト回答"):
        response = client.post("/api/chat", json={"question": "あ" * 1000})
    assert response.status_code == 200


def test_1001文字以上の質問はエラーになる():
    with patch("app.services.chat_service.ask") as mock_ask:
        response = client.post("/api/chat", json={"question": "あ" * 1001})
    assert response.status_code == 422
    mock_ask.assert_not_called()


def test_AIに接続できないと503とメッセージが返る():
    error = openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
    with patch("app.services.chat_service.ask", side_effect=error):
        response = client.post("/api/chat", json={"question": "LangChainとは？"})
    assert response.status_code == 503
    assert response.json() == {"detail": "AIに接続できませんでした。時間をおいて再度お試しください"}


def test_APIキーがあれば起動できる():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with TestClient(app) as started_client:
            assert started_client.get("/").status_code == 200


def test_APIキーがないと起動時にエラーになる():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            with TestClient(app):
                pass


def test_サービスがモデルの返答の文章を返す():
    # ChatOpenAI をモックに差し替え、ask が content を返すことを確かめる
    with patch("app.services.chat_service.ChatOpenAI") as mock_cls:
        mock_cls.return_value.invoke.return_value.content = "モデルの返答"
        assert chat_service.ask("質問") == "モデルの返答"
    mock_cls.assert_called_once_with(model=config.MODEL_NAME)
