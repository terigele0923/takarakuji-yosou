from dataclasses import dataclass

from app.schemas.lottery import RULES, Draw, LotteryType
from app.schemas.predict import CooccurrenceMatrix, FrequencyMatrix


@dataclass(frozen=True)
class CandidateTrend:
    score: float
    average_distance: float
    closest_round: int
    closest_distance: float
    match_distribution: list[int]


def candidate_trend(
    lottery: LotteryType,
    numbers: list[int],
    draws: list[Draw],
) -> CandidateTrend:
    """過去の全抽せんとの距離分布から、候補組の傾向スコアを計算する。"""
    rule = RULES[lottery]
    distribution = [0] * (rule.count + 1)
    distances: list[tuple[int, float]] = []

    for draw in draws:
        if rule.by_position:
            matches = sum(left == right for left, right in zip(numbers, draw.numbers))
            distance = 1 - matches / rule.count
        else:
            matches = len(set(numbers) & set(draw.numbers))
            union_size = 2 * rule.count - matches
            distance = 1 - matches / union_size
        distribution[matches] += 1
        distances.append((draw.round, distance))

    average_distance = sum(distance for _, distance in distances) / len(distances)
    closest_distance = min(distance for _, distance in distances)
    closest_round = max(
        round_number
        for round_number, distance in distances
        if distance == closest_distance
    )
    return CandidateTrend(
        score=round((1 - average_distance) * 100, 2),
        average_distance=round(average_distance, 4),
        closest_round=closest_round,
        closest_distance=round(closest_distance, 4),
        match_distribution=distribution,
    )


def build_history_matrices(
    lottery: LotteryType,
    draws: list[Draw],
) -> tuple[list[FrequencyMatrix], list[CooccurrenceMatrix]]:
    """全保存期間の番号頻度とペアの条件付き同時出現割合を集計する。"""
    rule = RULES[lottery]
    numbers = list(range(rule.min, rule.max + 1))
    frequencies: list[FrequencyMatrix] = []
    cooccurrences: list[CooccurrenceMatrix] = []

    if rule.by_position:
        for first_position in range(rule.count):
            position_counts = [
                sum(draw.numbers[first_position] == number for draw in draws)
                for number in numbers
            ]
            frequencies.append(
                FrequencyMatrix(
                    title=f"左から{first_position + 1}桁目の出現回数",
                    labels=[str(number) for number in numbers],
                    counts=position_counts,
                    total_draws=len(draws),
                )
            )

        for first_position in range(rule.count):
            for second_position in range(first_position + 1, rule.count):
                row_counts = [
                    sum(draw.numbers[first_position] == number for draw in draws)
                    for number in numbers
                ]
                counts = [
                    [
                        sum(
                            draw.numbers[first_position] == first
                            and draw.numbers[second_position] == second
                            for draw in draws
                        )
                        for second in numbers
                    ]
                    for first in numbers
                ]
                cooccurrences.append(
                    _cooccurrence_matrix(
                        f"左から{first_position + 1}桁目 × 左から{second_position + 1}桁目",
                        numbers,
                        numbers,
                        counts,
                        row_counts,
                    )
                )
        return frequencies, cooccurrences

    counts = [
        sum(number in draw.numbers for draw in draws)
        for number in numbers
    ]
    frequencies.append(
        FrequencyMatrix(
            title="本数字の出現回数",
            labels=[str(number) for number in numbers],
            counts=counts,
            total_draws=len(draws),
        )
    )
    pair_counts = [
        [
            sum(first in draw.numbers and second in draw.numbers for draw in draws)
            for second in numbers
        ]
        for first in numbers
    ]
    cooccurrences.append(
        _cooccurrence_matrix(
            "本数字ペアの同時出現割合（行の番号が出た回のうち、列の番号も出た割合）",
            numbers,
            numbers,
            pair_counts,
            counts,
        )
    )
    return frequencies, cooccurrences


def _cooccurrence_matrix(
    title: str,
    row_numbers: list[int],
    column_numbers: list[int],
    counts: list[list[int]],
    row_draw_counts: list[int],
) -> CooccurrenceMatrix:
    probabilities = [
        [
            count / row_draw_counts[row_index] if row_draw_counts[row_index] else 0
            for count in row
        ]
        for row_index, row in enumerate(counts)
    ]
    return CooccurrenceMatrix(
        title=title,
        row_labels=[str(number) for number in row_numbers],
        column_labels=[str(number) for number in column_numbers],
        counts=counts,
        probabilities=probabilities,
        row_draw_counts=row_draw_counts,
    )
