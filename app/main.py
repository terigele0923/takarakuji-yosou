from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.routes import router
from app.config import STATIC_DIR, check_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時に API キーが設定されているか確かめる
    check_api_key()
    yield


app = FastAPI(title="宝くじ予想AI", lifespan=lifespan)
register_exception_handlers(app)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(router)


@app.get("/")
def index():
    """画面（index.html）を返す"""
    return FileResponse(STATIC_DIR / "index.html")
