"""Learn a Numbers3 bias-weight profile from a walk-forward report."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.model_profile_service import learn_numbers3_profile

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    arguments = parser.parse_args()
    profile = learn_numbers3_profile(arguments.report)
    print(f"モデル版: {profile.model_version}")
    print(
        f"学習重み: 長期 {profile.config.long_weight:.0%} / "
        f"直近 {profile.config.recent_weight:.0%} / "
        f"ペア {profile.config.pair_weight:.0%}"
    )
    print(
        f"学習期間: {profile.training_rounds}回 / "
        f"5セット中の完全一致 {profile.training_exact_hits}回 / "
        f"合計最良一致数 {profile.training_total_matches}"
    )
