"""Green is not informative for some metrics (an overcommit ratio under 1
just means "not overcommitted", a rare metric like dropped packets being
exactly 0 says nothing about health) -- excluded_when_green keeps them from
adding a free floor-0 to the weighted average while green. See
scoring.compute_composite() and each threshold module's EXCLUDED_WHEN_GREEN.
"""
import cluster
import host
import pytest
import scoring

BOUNDS = {f"m{i}": {"green_max": 1, "yellow_max": 2, "orange_max": 3} for i in range(10)}
WEIGHTS = {}
VALUE = {"green": 0.5, "yellow": 1.5, "orange": 2.5, "red": 9}


def composite(bands, excluded=frozenset()):
    values = {f"m{i}": (None if b == "unknown" else VALUE[b]) for i, b in enumerate(bands)}
    return scoring.compute_composite(values, BOUNDS, WEIGHTS, excluded)


def test_excluded_metric_green_does_not_dilute_the_average():
    # m0 excluded-and-green must not count; the other 9 are plain greens.
    without_exclusion = composite(["green"] * 10)
    with_exclusion = composite(["green"] * 10, excluded={"m0"})
    assert without_exclusion == with_exclusion == (0.0, "green", {f"m{i}": "green" for i in range(10)})


def test_excluded_metric_still_counts_once_it_leaves_green():
    # m0 excluded-when-green, but it is yellow here, so it counts like any
    # other metric.
    score, band, _ = composite(["yellow"] + ["green"] * 9, excluded={"m0"})
    assert band == "yellow"
    assert score > 0.0


def test_every_known_metric_excluded_and_green_is_green_not_unknown():
    score, band, per = composite(["green"] * 3, excluded={"m0", "m1", "m2"})
    assert (score, band) == (0.0, "green")
    assert per == {"m0": "green", "m1": "green", "m2": "green"}


def test_excluded_green_mixed_with_a_worse_band_elsewhere():
    # The excluded-green metric can never push the band away from green;
    # the real signal (orange) still wins.
    score, band, _ = composite(["green", "orange"], excluded={"m0"})
    assert band == "orange"
    # Only m1 (orange, weight 1) feeds the weighted average: 0.7*80 + 0.3*80.
    assert score == round(0.7 * 80 + 0.3 * 80, 1)


def test_excluded_metric_red_is_not_hidden():
    score, band, _ = composite(["green"] * 9 + ["red"], excluded={"m0"})
    assert band == "red"
    assert score > 0


@pytest.mark.parametrize("scope, excluded_when_green", [(cluster, cluster.EXCLUDED_WHEN_GREEN), (host, host.EXCLUDED_WHEN_GREEN)])
def test_shipped_excluded_when_green_keys_are_real_metrics(scope, excluded_when_green):
    assert excluded_when_green
    assert excluded_when_green <= scope.BAND_BOUNDS.keys()
