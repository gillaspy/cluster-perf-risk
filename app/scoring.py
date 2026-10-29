"""
Weighted-worst-band composite scoring logic, shared by both object types.

Since 2.1.0 the composite BAND is the worst band among the known
sub-metrics, so a red sub-metric always makes the object red. The numeric
score keeps its formula; it is no longer the source of the band (one red
sub-metric among greens scores from 63, which the old score bands drew
yellow).
Takes each object type's own (band_bounds, weights) tables as arguments
instead of reading globals, so cluster.py and host.py -- or a future third
object type -- can each supply their own merged shared+own-scope tables.
"""
from __future__ import annotations

# Band floor scores used to compute the composite. green=0, yellow=60, orange=80, red=90
BAND_FLOORS = {"green": 0, "yellow": 60, "orange": 80, "red": 90, "unknown": 0}

# Numeric form of the composite band, published as "Risk Band Level" so
# dashboards can color by the band (widgets color by a number, not a string).
# No level for "unknown": nothing is published.
BAND_LEVELS = {"green": 0, "yellow": 1, "orange": 2, "red": 3}


def classify_band(value: float | None, metric_key: str, band_bounds: dict) -> str:
    """Return 'green' | 'yellow' | 'orange' | 'red' | 'unknown' for a metric value."""
    if value is None:
        return "unknown"
    bounds = band_bounds.get(metric_key)
    if bounds is None:
        return "unknown"
    if value <= bounds["green_max"]:
        return "green"
    if value <= bounds["yellow_max"]:
        return "yellow"
    if value <= bounds["orange_max"]:
        return "orange"
    return "red"


def compute_composite(
    metric_values: dict[str, float | None], band_bounds: dict, weights: dict
) -> tuple[float, str, dict[str, str]]:
    """
    metric_values: {metric_key: value_or_None}
    Returns (composite_score 0-100, composite_band, {metric_key: band})

    Score, weighted-worst-band: 70% weight on the single worst sub-metric's
    band floor, 30% on the weighted average across all sub-metrics. This keeps
    one red sub-metric from being diluted into invisibility by several green
    ones.

    Band: the worst band among the known sub-metrics (red > orange > yellow >
    green), "unknown" when none is known.
    """
    per_metric_band: dict[str, str] = {}
    weighted_scores = []
    total_weight = 0.0

    for key, value in metric_values.items():
        if key not in band_bounds:
            continue
        band = classify_band(value, key, band_bounds)
        per_metric_band[key] = band
        # Unknown metrics (null/missing collection) are excluded from the
        # composite math entirely -- otherwise their floor of 0 silently drags
        # the composite toward "green" even when real data is red/orange.
        if band == "unknown":
            continue
        weight = weights.get(key, 1.0)
        weighted_scores.append(BAND_FLOORS.get(band, 0) * weight)
        total_weight += weight

    known_bands = [b for b in per_metric_band.values() if b != "unknown"]
    if not known_bands or total_weight == 0:
        # Every sub-metric failed to collect -- report "unknown", not a false
        # "green". A broken collection should never look like a healthy cluster.
        return 0.0, "unknown", per_metric_band

    worst_band = max(known_bands, key=lambda b: BAND_FLOORS.get(b, 0))
    worst_floor = BAND_FLOORS.get(worst_band, 0)
    weighted_avg = sum(weighted_scores) / total_weight

    composite = round(min(100.0, max(0.0, 0.7 * worst_floor + 0.3 * weighted_avg)), 1)

    return composite, worst_band, per_metric_band


def metrics_in_worst_band(composite_band: str, per_metric_band: dict[str, str]) -> int | None:
    """How many known sub-metrics are in the composite (worst) band. None
    when the band is unknown."""
    if composite_band not in BAND_LEVELS:
        return None
    return sum(1 for band in per_metric_band.values() if band == composite_band)
