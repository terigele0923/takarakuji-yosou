"""Run a two-month walk-forward evaluation without modifying the real DB."""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.lottery import LotteryType
from app.services.walk_forward_evaluation_service import run_walk_forward_evaluation


def main() -> None:
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, default=Path("data/lottery.db"))
    parser.add_argument("--mock-db", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--months", type=int, default=2)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--random-samples", type=int, default=200)
    parser.add_argument("--lottery", choices=[item.value for item in LotteryType])
    arguments = parser.parse_args()
    mock_db = arguments.mock_db or Path(f"data/walk_forward_mock-{timestamp}.db")
    report_path = arguments.report or Path(
        f"data/walk_forward_report-{timestamp}.json"
    )

    report = run_walk_forward_evaluation(
        arguments.source_db,
        mock_db,
        report_path,
        arguments.months,
        arguments.count,
        arguments.random_samples,
        [LotteryType(arguments.lottery)] if arguments.lottery else None,
    )
    print(f"対象期間: {report['cutoff_date']} より後 〜 {report['latest_date']}")
    for summary in report["summaries"]:
        print(
            f"{summary['lottery']}: {summary['evaluated_rounds']}回 / "
            f"平均一致 {summary['average_best_matches']:.4f} / "
            f"ランダム {summary['random_average_best_matches']:.4f} / "
            f"差 {summary['match_lift']:+.4f} / "
            f"完全一致 {summary['exact_hits']}回"
        )
    print(f"モックDB: {mock_db.resolve()}")
    print(f"詳細レポート: {report_path.resolve()}")


if __name__ == "__main__":
    main()
