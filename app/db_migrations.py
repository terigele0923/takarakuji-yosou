from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import BASE_DIR, DB_PATH


def upgrade_database(database_path: Path = DB_PATH) -> None:
    """現在設定されているDBへ未適用マイグレーションを適用する。"""
    ini_path = Path(BASE_DIR) / "alembic.ini"
    alembic_config = Config(str(ini_path))
    alembic_config.attributes["database_path"] = Path(database_path)
    command.upgrade(alembic_config, "head")
