import datetime

import pytest

from app.schemas.lottery import Draw, LotteryType
from app.services.trend_service import build_history_matrices, candidate_trend


def test_loto_trend_uses_jaccard_distance_and_match_distribution():
    draws = [
        Draw(round=1, draw_date=datetime.date(2026, 1, 5), numbers=[1, 5, 12, 19, 30, 41], bonus=[22]),
        Draw(round=2, draw_date=datetime.date(2026, 1, 8), numbers=[3, 11, 20, 28, 35, 43], bonus=[7]),
    ]

    trend = candidate_trend(LotteryType.LOTO6, draws[0].numbers, draws)

    assert trend.score == 50
    assert trend.average_distance == 0.5
    assert trend.closest_round == 1
    assert trend.closest_distance == 0
    assert trend.match_distribution == [1, 0, 0, 0, 0, 0, 1]


def test_numbers_trend_keeps_digit_positions():
    draws = [
        Draw(round=1, draw_date=datetime.date(2026, 1, 5), numbers=[0, 8, 8], bonus=[]),
    ]

    trend = candidate_trend(LotteryType.NUMBERS3, [0, 8, 9], draws)

    assert trend.score == pytest.approx(66.67)
    assert trend.average_distance == pytest.approx(0.3333)
    assert trend.closest_round == 1
    assert trend.match_distribution == [0, 0, 1, 0]


def test_loto_history_matrices_show_frequency_and_conditional_pair_rates():
    draws = [
        Draw(round=1, draw_date=datetime.date(2026, 1, 5), numbers=[1, 2, 3, 4, 5], bonus=[6]),
        Draw(round=2, draw_date=datetime.date(2026, 1, 8), numbers=[1, 7, 8, 9, 10], bonus=[11]),
    ]

    frequencies, cooccurrences = build_history_matrices(LotteryType.MINILOTO, draws)

    assert frequencies[0].counts[:3] == [2, 1, 1]
    matrix = cooccurrences[0]
    assert matrix.counts[0][:3] == [2, 1, 1]
    assert matrix.probabilities[0][:3] == [1, 0.5, 0.5]
    assert matrix.row_draw_counts[0] == 2


def test_numbers_history_matrices_are_separated_by_digit_position():
    draws = [
        Draw(round=1, draw_date=datetime.date(2026, 1, 5), numbers=[1, 2, 3], bonus=[]),
        Draw(round=2, draw_date=datetime.date(2026, 1, 8), numbers=[1, 4, 3], bonus=[]),
    ]

    frequencies, cooccurrences = build_history_matrices(LotteryType.NUMBERS3, draws)

    assert len(frequencies) == 3
    assert frequencies[0].counts[1] == 2
    assert len(cooccurrences) == 3
    first_two_positions = cooccurrences[0]
    assert first_two_positions.counts[1][2] == 1
    assert first_two_positions.counts[1][4] == 1
    assert first_two_positions.probabilities[1][2] == 0.5
