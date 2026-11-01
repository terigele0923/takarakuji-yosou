"""Repeat loss-feedback learning and verify it on a separate date range."""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.advanced_model_training_service import (
    train_numbers3_iteratively,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loops", type=int, default=5)
    parser.add_argument("--learning-start", default="2016-01-01")
    parser.add_argument("--learning-end", default="2025-12-31")
    parser.add_argument("--test-start", default="2026-01-01")
    parser.add_argument("--test-end")
    arguments = parser.parse_args()
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = Path(f"data/advanced_training_report-{timestamp}.json")
    report = train_numbers3_iteratively(
        report_path=report_path,
        loops=arguments.loops,
        learning_start=datetime.date.fromisoformat(arguments.learning_start),
        learning_end=datetime.date.fromisoformat(arguments.learning_end),
        test_start=datetime.date.fromisoformat(arguments.test_start),
        test_end=(
            datetime.date.fromisoformat(arguments.test_end)
            if arguments.test_end
            else None
        ),
    )
    metrics = report["challenger"]["metrics"]
    config = report["challenger"]["config"]
    print(
        f"候補設定: 長期 {config['long_weight']:.0%} / "
        f"直近 {config['recent_weight']:.0%} / "
        f"ペア {config['pair_weight']:.0%} / "
        f"半減期 {config['recent_half_life']}回"
    )
    print(
        f"未使用期間: {metrics['evaluated_draws']}回 / "
        f"平均順位 {metrics['mean_actual_rank']:.2f} / "
        f"平均一致差 {metrics['match_lift']:+.4f} / "
        f"95%信頼区間 [{metrics['confidence_low']:+.4f}, "
        f"{metrics['confidence_high']:+.4f}] / "
        f"完全一致 {metrics['exact_hits']}回"
    )
    print("本番昇格: " + ("実施" if report["promoted"] else "見送り"))
    print(f"詳細レポート: {report_path.resolve()}")
