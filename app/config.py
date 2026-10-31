import os
from pathlib import Path

from dotenv import load_dotenv

# .env ファイルから OPENAI_API_KEY を読み込む
load_dotenv()

# 画面ファイル（HTML・CSS・JS）の置き場所
STATIC_DIR = Path(__file__).resolve().parent / "static"

# プロジェクトのフォルダ
BASE_DIR = Path(__file__).resolve().parent.parent

# 過去の抽選結果を保存する SQLite のファイル
# 環境変数 LOTTERY_DB_PATH があればそのファイルを使う（相対パスはプロジェクトのフォルダから）
DEFAULT_DB_PATH = BASE_DIR / "data" / "lottery.db"
DB_PATH = BASE_DIR / os.getenv("LOTTERY_DB_PATH", DEFAULT_DB_PATH)

# 使用するモデル
MODEL_NAME = "gpt-5.4-mini"

# 集計の対象にする期間（最新の抽選日から何年前までか）
STATS_YEARS = 10


def check_api_key() -> None:
    """OPENAI_API_KEY が設定されていなければエラーにする"""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY が設定されていません。.env を確認してください")
