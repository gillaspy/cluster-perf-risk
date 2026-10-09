"""
Host-scope scoring. The metric values come from
traversal.collect_cluster_and_host_metrics() (computed from just this host's
own VMs); the results are projected onto the native HostSystem by
native_projection.py.
"""
from typing import Optional

import scoring
import thresholds_host
import thresholds_shared

# Merged so compute_composite() sees both this object type's own bounds/weights
# and the ones it shares with the cluster object.
BAND_BOUNDS = {**thresholds_shared.BAND_BOUNDS, **thresholds_host.BAND_BOUNDS}
WEIGHTS = {**thresholds_shared.WEIGHTS, **thresholds_host.WEIGHTS}


def score(host_metric_values: dict[str, Optional[float]]) -> tuple:
    """Returns (composite_score, composite_band, {metric_key: band})."""
    return scoring.compute_composite(host_metric_values, BAND_BOUNDS, WEIGHTS)
