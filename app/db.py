import sqlite3
from pathlib import Path

from app.config import DB_PATH


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """SQLite に接続する（列名で値を取り出せるようにする）"""
    if not db_path.exists():
        raise FileNotFoundError(
            f"DB のファイルがありません: {db_path}。README の手順で表を作ってください"
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
