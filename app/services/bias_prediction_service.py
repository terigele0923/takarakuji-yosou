import hashlib
import itertools
import math
import random
from dataclasses import dataclass

from app.schemas.lottery import RULES, Draw, LotteryType

MODEL_VERSION = "bias-v1"


@dataclass(frozen=True)
class BiasPredictionConfig:
    """偏り予測の調整値。検証時に別設定を注入できる。"""

    recent_half_life: int = 40
    smoothing_strength: float = 8.0
    beam_width: int = 4_000
    backtest_draws: int = 40
    backtest_random_samples: int = 200
    long_weight: float = 0.30
    recent_weight: float = 0.50
    pair_weight: float = 0.20

    def __post_init__(self) -> None:
        if self.recent_half_life <= 0 or self.smoothing_strength <= 0:
            raise ValueError("半減期と平滑化強度は正数で指定してください")
        if self.beam_width <= 0 or self.backtest_draws <= 0 or self.backtest_random_samples <= 0:
            raise ValueError("探索幅とバックテスト件数は正数で指定してください")
        if not math.isclose(self.long_weight + self.recent_weight + self.pair_weight, 1.0):
            raise ValueError("偏りスコアの重み合計は1にしてください")


DEFAULT_CONFIG = BiasPredictionConfig()


@dataclass(frozen=True)
class BiasModel:
    lottery: LotteryType
    individual_long: tuple[tuple[float, ...], ...]
    individual_recent: tuple[tuple[float, ...], ...]
    pair_lifts: dict[tuple[int, int, int, int], float]


@dataclass(frozen=True)
class ScoredCandidate:
    numbers: tuple[int, ...]
    raw_score: float
    long_score: float
    recent_score: float
    pair_score: float


@dataclass(frozen=True)
class BacktestResult:
    evaluated_draws: int
    actual_average_score: float
    random_average_score: float
    score_lift_percent: float
    above_random_rate: float


def build_bias_model(
    lottery: LotteryType,
    draws: list[Draw],
    config: BiasPredictionConfig = DEFAULT_CONFIG,
) -> BiasModel:
    """過去結果から長期・直近・ペアの偏りを平滑化して推定する。"""
    rule = RULES[lottery]
    domain_size = rule.max - rule.min + 1
    positions = rule.count if rule.by_position else 1
    expected_individual = 1 / domain_size if rule.by_position else rule.count / domain_size
    long_counts = [[0.0] * domain_size for _ in range(positions)]
    recent_counts = [[0.0] * domain_size for _ in range(positions)]
    pair_counts: dict[tuple[int, int, int, int], float] = {}
    total_recent_weight = 0.0

    for age, draw in enumerate(reversed(draws)):
        weight = 0.5 ** (age / config.recent_half_life)
        total_recent_weight += weight
        positioned = (
            list(enumerate(draw.numbers))
            if rule.by_position
            else [(0, number) for number in sorted(draw.numbers)]
        )
        for position, number in positioned:
            index = number - rule.min
            long_counts[position][index] += 1
            recent_counts[position][index] += weight

        for left_index, (left_position, left_number) in enumerate(positioned):
            for right_position, right_number in positioned[left_index + 1 :]:
                if not rule.by_position and left_number > right_number:
                    left_number, right_number = right_number, left_number
                key = (left_position, left_number, right_position, right_number)
                pair_counts[key] = pair_counts.get(key, 0.0) + weight

    individual_long = tuple(
        tuple(_smoothed_lift(count, len(draws), expected_individual, config) for count in counts)
        for counts in long_counts
    )
    individual_recent = tuple(
        tuple(_smoothed_lift(count, total_recent_weight, expected_individual, config) for count in counts)
        for counts in recent_counts
    )

    pair_lifts = {}
    expected_pair = (
        1 / (domain_size * domain_size)
        if rule.by_position
        else rule.count * (rule.count - 1) / (domain_size * (domain_size - 1))
    )
    for key, count in pair_counts.items():
        pair_lifts[key] = _smoothed_lift(
            count,
            total_recent_weight,
            expected_pair,
            config,
        )
    return BiasModel(
        lottery=lottery,
        individual_long=individual_long,
        individual_recent=individual_recent,
        pair_lifts=pair_lifts,
    )


def generate_candidates(
    model: BiasModel,
    count: int,
    config: BiasPredictionConfig = DEFAULT_CONFIG,
) -> list[ScoredCandidate]:
    """偏りスコア上位から、互いに似すぎない候補を選ぶ。"""
    rule = RULES[model.lottery]
    values = range(rule.min, rule.max + 1)
    if rule.by_position:
        candidates = (
            _score_candidate(model, numbers, config)
            for numbers in itertools.product(values, repeat=rule.count)
        )
        ranked = sorted(candidates, key=lambda item: (-item.raw_score, item.numbers))
    else:
        ranked = _beam_candidates(model, config)

    selected = []
    max_overlap = max(rule.count - 2, 0)
    for candidate in ranked:
        if all(_overlap(rule.by_position, candidate.numbers, other.numbers) <= max_overlap for other in selected):
            selected.append(candidate)
            if len(selected) == count:
                break
    if len(selected) < count:
        for candidate in ranked:
            if candidate not in selected:
                selected.append(candidate)
                if len(selected) == count:
                    break
    return selected


def normalize_scores(candidates: list[ScoredCandidate]) -> list[float]:
    """候補の偏り強度を0〜100の表示用スコアに変換する。"""
    if not candidates:
        return []
    return [round(100 / (1 + math.exp(-candidate.raw_score)), 2) for candidate in candidates]


def backtest_bias(
    lottery: LotteryType,
    draws: list[Draw],
    config: BiasPredictionConfig = DEFAULT_CONFIG,
) -> BacktestResult:
    """各時点より前のデータだけで、実結果の偏りスコアをランダム候補と比較する。"""
    minimum_training = max(30, RULES[lottery].count * 5)
    test_start = max(minimum_training, len(draws) - config.backtest_draws)
    if test_start >= len(draws):
        return BacktestResult(0, 0, 0, 0, 0)

    actual_scores = []
    random_scores = []
    above_random = 0
    for index in range(test_start, len(draws)):
        model = build_bias_model(lottery, draws[:index], config)
        actual = _score_candidate(model, tuple(draws[index].numbers), config).raw_score
        rng = random.Random(_stable_seed(lottery, draws[index].round))
        samples = [
            _score_candidate(model, _random_candidate(lottery, rng), config).raw_score
            for _ in range(config.backtest_random_samples)
        ]
        random_average = sum(samples) / len(samples)
        actual_scores.append(actual)
        random_scores.append(random_average)
        above_random += actual > random_average

    actual_average = sum(actual_scores) / len(actual_scores)
    random_average = sum(random_scores) / len(random_scores)
    return BacktestResult(
        evaluated_draws=len(actual_scores),
        actual_average_score=round(actual_average, 4),
        random_average_score=round(random_average, 4),
        score_lift_percent=round((math.exp(actual_average - random_average) - 1) * 100, 2),
        above_random_rate=round(above_random / len(actual_scores), 4),
    )


def describe_candidate(candidate: ScoredCandidate) -> str:
    components = [
        (candidate.recent_score, "直近の時間加重頻度"),
        (candidate.long_score, "長期出現頻度"),
        (candidate.pair_score, "番号ペアの共起傾向"),
    ]
    components.sort(reverse=True)
    return f"{components[0][1]}と{components[1][1]}を強く反映した候補です。"


def _smoothed_lift(
    count: float,
    total: float,
    expected: float,
    config: BiasPredictionConfig,
) -> float:
    observed = (count + config.smoothing_strength * expected) / (
        total + config.smoothing_strength
    )
    return math.log(max(observed / expected, 1e-12))


def _score_candidate(
    model: BiasModel,
    numbers: tuple[int, ...],
    config: BiasPredictionConfig = DEFAULT_CONFIG,
) -> ScoredCandidate:
    rule = RULES[model.lottery]
    positioned = (
        list(enumerate(numbers))
        if rule.by_position
        else [(0, number) for number in sorted(numbers)]
    )
    long_values = [model.individual_long[position][number - rule.min] for position, number in positioned]
    recent_values = [model.individual_recent[position][number - rule.min] for position, number in positioned]
    pair_values = []
    for left_index, (left_position, left_number) in enumerate(positioned):
        for right_position, right_number in positioned[left_index + 1 :]:
            if not rule.by_position and left_number > right_number:
                left_number, right_number = right_number, left_number
            pair_values.append(model.pair_lifts.get((left_position, left_number, right_position, right_number), 0.0))
    long_score = sum(long_values) / len(long_values)
    recent_score = sum(recent_values) / len(recent_values)
    pair_score = sum(pair_values) / len(pair_values) if pair_values else 0.0
    raw_score = (
        config.long_weight * long_score
        + config.recent_weight * recent_score
        + config.pair_weight * pair_score
    )
    return ScoredCandidate(numbers, raw_score, long_score, recent_score, pair_score)


def _beam_candidates(
    model: BiasModel, config: BiasPredictionConfig
) -> list[ScoredCandidate]:
    rule = RULES[model.lottery]
    beam: list[tuple[int, ...]] = [()]
    for _ in range(rule.count):
        expanded = []
        for partial in beam:
            start = partial[-1] + 1 if partial else rule.min
            remaining_after_pick = rule.count - len(partial) - 1
            for number in range(start, rule.max - remaining_after_pick + 1):
                candidate = partial + (number,)
                expanded.append((_score_partial(model, candidate, config), candidate))
        expanded.sort(key=lambda item: (-item[0], item[1]))
        beam = [candidate for _, candidate in expanded[: config.beam_width]]
    return sorted(
        (_score_candidate(model, candidate, config) for candidate in beam),
        key=lambda item: (-item.raw_score, item.numbers),
    )


def _score_partial(
    model: BiasModel,
    numbers: tuple[int, ...],
    config: BiasPredictionConfig,
) -> float:
    return _score_candidate(model, numbers, config).raw_score


def _overlap(by_position: bool, left: tuple[int, ...], right: tuple[int, ...]) -> int:
    if by_position:
        return sum(a == b for a, b in zip(left, right))
    return len(set(left) & set(right))


def _random_candidate(lottery: LotteryType, rng: random.Random) -> tuple[int, ...]:
    rule = RULES[lottery]
    values = range(rule.min, rule.max + 1)
    if rule.by_position:
        return tuple(rng.choice(values) for _ in range(rule.count))
    return tuple(sorted(rng.sample(list(values), rule.count)))


def _stable_seed(lottery: LotteryType, round_number: int) -> int:
    digest = hashlib.sha256(f"{lottery.value}:{round_number}".encode()).digest()
    return int.from_bytes(digest[:8])
