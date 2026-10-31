"""Start the local FastAPI server without invoking uvicorn.exe directly."""

import sys
from pathlib import Path

# scripts フォルダーから実行しても、プロジェクト直下の app を読み込めるようにする。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn

from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
