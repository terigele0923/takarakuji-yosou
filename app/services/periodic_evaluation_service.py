import asyncio
import logging

from app.services.prediction_tracking_service import evaluate_pending

logger = logging.getLogger(__name__)


async def run_periodic_evaluations(interval_hours: float) -> None:
    """サーバー稼働中、未評価の最新抽選データを一定間隔で確認する。"""
    interval_seconds = max(interval_hours * 60 * 60, 60)
    while True:
        try:
            await asyncio.to_thread(evaluate_pending)
        except Exception:
            logger.exception("偏りモデルの定期評価に失敗しました")
        await asyncio.sleep(interval_seconds)
