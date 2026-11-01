"""Evaluate the bias model for lottery data versions not evaluated yet."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.prediction_tracking_service import evaluate_pending

if __name__ == "__main__":
    evaluations = evaluate_pending()
    if not evaluations:
        print("新しく評価する抽選データはありません。")
    for evaluation in evaluations:
        print(
            f"{evaluation.lottery.value}: 第{evaluation.source_last_round}回まで / "
            f"上振れ率 {evaluation.above_random_rate:.1%} / "
            f"スコア差 {evaluation.score_lift_percent:.2f}%"
        )
