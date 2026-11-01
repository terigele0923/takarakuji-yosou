import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.routes import router
from app.config import (
    MODEL_EVALUATION_ENABLED,
    MODEL_EVALUATION_INTERVAL_HOURS,
    STATIC_DIR,
    check_api_key,
)
from app.services.periodic_evaluation_service import run_periodic_evaluations


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時に API キーが設定されているか確かめる
    check_api_key()
    evaluation_task = None
    if MODEL_EVALUATION_ENABLED:
        evaluation_task = asyncio.create_task(
            run_periodic_evaluations(MODEL_EVALUATION_INTERVAL_HOURS)
        )
    try:
        yield
    finally:
        if evaluation_task is not None:
            evaluation_task.cancel()
            with suppress(asyncio.CancelledError):
                await evaluation_task


app = FastAPI(title="宝くじ予想AI", lifespan=lifespan)
register_exception_handlers(app)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(router)


@app.get("/")
def index():
    """画面（index.html）を返す"""
    return FileResponse(STATIC_DIR / "index.html")
