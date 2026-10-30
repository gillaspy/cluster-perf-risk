"""2.1.0 item 3: the composite band is the worst known sub-metric band; the
score formula is unchanged. The dashboard is tested in test_dashboard.py."""
import pytest
import scoring

BOUNDS = {f"m{i}": {"green_max": 1, "yellow_max": 2, "orange_max": 3} for i in range(10)}
WEIGHTS = {}
VALUE = {"green": 0.5, "yellow": 1.5, "orange": 2.5, "red": 9}


def composite(*bands):
    values = {f"m{i}": (None if b == "unknown" else VALUE[b]) for i, b in enumerate(bands)}
    return scoring.compute_composite(values, BOUNDS, WEIGHTS)


@pytest.mark.parametrize("odd", ["red", "orange", "yellow"])
def test_single_bad_sub_metric_among_many_greens_sets_the_band(odd):
    score, band, per = composite(*(["green"] * 8 + [odd]))
    assert band == odd
    assert scoring.metrics_in_worst_band(band, per) == 1


def test_single_red_among_greens_was_yellow_by_score():
    # The case that motivated the change: the score stays as it was (66),
    # which the old score bands drew yellow.
    score, band, _ = composite(*(["green"] * 8 + ["red"]))
    assert score == round(0.7 * 90 + 0.3 * (90 / 9), 1) == 66.0
    assert band == "red"


def test_all_green():
    score, band, per = composite("green", "green", "green")
    assert (score, band) == (0.0, "green")
    assert scoring.metrics_in_worst_band(band, per) == 3


def test_all_unknown():
    score, band, per = composite("unknown", "unknown")
    assert (score, band) == (0.0, "unknown")
    assert scoring.metrics_in_worst_band(band, per) is None


def test_unknown_is_excluded_from_band_and_count():
    _, band, per = composite("unknown", "yellow", "green", "yellow")
    assert band == "yellow"
    assert scoring.metrics_in_worst_band(band, per) == 2


def test_score_formula_unchanged():
    # 0.7 * worst floor + 0.3 * weighted average of floors (weights default 1).
    score, _, _ = composite("green", "yellow", "orange")
    assert score == round(0.7 * 80 + 0.3 * (0 + 60 + 80) / 3, 1)


def test_band_levels():
    assert scoring.BAND_LEVELS == {"green": 0, "yellow": 1, "orange": 2, "red": 3}

