import sqlite3

import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

AI_ERROR_MESSAGE = "AIに接続できませんでした。時間をおいて再度お試しください"
DB_ERROR_MESSAGE = "抽選結果のデータベースが準備されていません"


def register_exception_handlers(app: FastAPI) -> None:
    """複数APIで共通する外部AI・DBエラーを同じHTTP応答へ変換する。"""

    @app.exception_handler(openai.APIError)
    async def handle_ai_error(_request: Request, _error: openai.APIError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": AI_ERROR_MESSAGE})

    async def handle_db_error(_request: Request, _error: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": DB_ERROR_MESSAGE})

    app.add_exception_handler(FileNotFoundError, handle_db_error)
    app.add_exception_handler(sqlite3.OperationalError, handle_db_error)
