"""
Cluster-scope metrics and scoring: the cluster-only derived metrics (ballooned
%, CPU imbalance proxy, network throughput %, vMotion %) and the composite
score. The results are projected onto the native ClusterComputeResource by
native_projection.py. Metrics shared with the host scope come from
traversal.py instead.
"""
import statistics
from typing import Optional

from aria.ops.suite_api_client import SuiteApiClient
from constants_cluster import CLUSTER_LEVEL_METRICS
from constants_cluster import HOST_LINKSPEED_PROPERTY
from constants_cluster import METRIC_CLUSTER_CPU_IMBALANCE
from constants_cluster import METRIC_CPU_THREAD_UTILIZATION
from constants_cluster import METRIC_HOST_CPU_IMBALANCE
from constants_cluster import METRIC_MEMORY_BALLOONED
from constants_cluster import METRIC_NETWORK_THROUGHPUT
from constants_cluster import METRIC_VMOTION_PCT
from constants_cluster import NATIVE_STATKEY_MAP
from constants_cluster import NETWORK_USAGE_AVERAGE_STATKEY
from constants_cluster import NUMBER_VMOTION_STATKEY
from constants_cluster import VM_COUNT_PER_HOST_STATKEY
from constants_shared import MEMORY_BALLOON_KB_STATKEY
from constants_shared import MEMORY_TOTAL_CAPACITY_KB_STATKEY
import scoring
import thresholds_cluster
import thresholds_shared
from suite_api import fetch_child_hosts
from suite_api import get_property
from suite_api import latest_stat

# Merged so compute_composite() sees both this object type's own bounds/weights
# and the ones it shares with the host object.
BAND_BOUNDS = {**thresholds_shared.BAND_BOUNDS, **thresholds_cluster.BAND_BOUNDS}
WEIGHTS = {**thresholds_shared.WEIGHTS, **thresholds_cluster.WEIGHTS}


def gather_metric_values(client: SuiteApiClient, cluster_id: str) -> dict[str, Optional[float]]:
    """Cluster-only metrics: the NATIVE_STATKEY_MAP-driven ones plus the four
    derived helpers below. Metrics shared with the host object (worst/p90 VM
    metrics, monster VM ratios, host memory contention/dropped packets) are
    filled in separately by traversal.collect_cluster_and_host_metrics()."""
    metric_values: dict[str, Optional[float]] = {}
    for metric_key, statkey in NATIVE_STATKEY_MAP.items():
        if metric_key in CLUSTER_LEVEL_METRICS:
            metric_values[metric_key] = latest_stat(client, cluster_id, statkey)
        else:
            metric_values[metric_key] = _highest_host_stat(client, cluster_id, statkey)

    metric_values[METRIC_MEMORY_BALLOONED] = _highest_host_ballooned_pct(client, cluster_id)
    metric_values[METRIC_HOST_CPU_IMBALANCE] = _host_cpu_imbalance_pct(client, cluster_id)
    metric_values[METRIC_NETWORK_THROUGHPUT] = _network_throughput_pct(client, cluster_id)
    metric_values[METRIC_VMOTION_PCT] = _vmotion_pct(client, cluster_id)

    # clusterServices|total_imbalance comes back from the Suite API as a raw
    # scaled integer despite its unitless appearance -- confirmed 2026-08-15
    # via the VCF Operations UI tooltip (see thresholds_cluster.py).
    if metric_values.get(METRIC_CLUSTER_CPU_IMBALANCE) is not None:
        metric_values[METRIC_CLUSTER_CPU_IMBALANCE] /= 1000

    return metric_values


def score(metric_values: dict[str, Optional[float]]) -> tuple:
    """Returns (composite_score, composite_band, {metric_key: band})."""
    return scoring.compute_composite(metric_values, BAND_BOUNDS, WEIGHTS)


def _highest_host_stat(client: SuiteApiClient, cluster_id: str, statkey: str) -> Optional[float]:
    host_ids = fetch_child_hosts(client, cluster_id)

    values = [
        v
        for v in (latest_stat(client, host_id, statkey) for host_id, _host_name in host_ids)
        if v is not None
    ]
    return max(values) if values else None


def _highest_host_ballooned_pct(client: SuiteApiClient, cluster_id: str) -> Optional[float]:
    """
    memory_ballooned_pct has no native percentage statkey. Computed per host as
    (ballooned KB / total host memory KB) * 100, then the max across hosts in
    the cluster is returned (matching the matrix's "Highest ESXi ..." framing).
    """
    host_ids = fetch_child_hosts(client, cluster_id)

    ratios = []
    for host_id, _host_name in host_ids:
        ballooned_kb = latest_stat(client, host_id, MEMORY_BALLOON_KB_STATKEY)
        total_kb = latest_stat(client, host_id, MEMORY_TOTAL_CAPACITY_KB_STATKEY)
        if ballooned_kb is not None and total_kb:
            ratios.append((ballooned_kb / total_kb) * 100)

    return max(ratios) if ratios else None


def _host_cpu_imbalance_pct(client: SuiteApiClient, cluster_id: str) -> Optional[float]:
    """
    No per-host CPU imbalance statkey exists -- the only real DRS imbalance
    metric (clusterServices|total_imbalance, see METRIC_CLUSTER_CPU_IMBALANCE)
    is cluster-level. This is a synthetic proxy for the matrix's "Highest ESXi
    CPU Imbalance" row: population standard deviation, in percentage points, of
    cpu|utilization_average across the cluster's hosts. Needs at least 2 hosts
    with data to be meaningful.
    """
    host_ids = fetch_child_hosts(client, cluster_id)
    cpu_statkey = NATIVE_STATKEY_MAP[METRIC_CPU_THREAD_UTILIZATION]

    values = [
        v
        for v in (latest_stat(client, host_id, cpu_statkey) for host_id, _host_name in host_ids)
        if v is not None
    ]
    return statistics.pstdev(values) if len(values) >= 2 else None


def _network_throughput_pct(client: SuiteApiClient, cluster_id: str) -> Optional[float]:
    """
    net|usage_capacity (previously used here) is NOT usable despite catalog
    metadata claiming unit "%" -- see constants_cluster.py for the full story.
    This derives the real percentage instead: per host, (net|usage_average
    KBps converted to Mbps) / (config|network|linkspeed Mbps, a resource
    PROPERTY fetched via a different endpoint than stats) * 100, then max
    across the cluster's hosts -- the matrix's established "highest across
    hosts" pattern.
    """
    host_ids = fetch_child_hosts(client, cluster_id)

    ratios = []
    for host_id, _host_name in host_ids:
        usage_kbps = latest_stat(client, host_id, NETWORK_USAGE_AVERAGE_STATKEY)
        linkspeed_str = get_property(client, host_id, HOST_LINKSPEED_PROPERTY)
        if usage_kbps is None or not linkspeed_str:
            continue
        try:
            linkspeed_mbps = float(linkspeed_str)
        except ValueError:
            continue
        if linkspeed_mbps:
            ratios.append((usage_kbps * 8 / 1000) / linkspeed_mbps * 100)

    return max(ratios) if ratios else None


def _vmotion_pct(client: SuiteApiClient, cluster_id: str) -> Optional[float]:
    """
    No native statkey combines these into a ready percentage.
    summary|vm_count_per_host is an AVERAGE, not a cluster VM total -- but
    confirmed live that vm_count_per_host * host_count reproduces the
    cluster's real VM count exactly, so it's used as the total-VM estimator.
    summary|number_vmotion is a raw event count for the current collection
    interval. See constants_cluster.py -- bounds here are unverified against
    real-world vMotion behavior.
    """
    host_ids = fetch_child_hosts(client, cluster_id)
    host_count = len(host_ids)
    if not host_count:
        return None

    vm_count_per_host = latest_stat(client, cluster_id, VM_COUNT_PER_HOST_STATKEY)
    vmotion_count = latest_stat(client, cluster_id, NUMBER_VMOTION_STATKEY)
    if vm_count_per_host is None or vmotion_count is None:
        return None

    total_vm_estimate = vm_count_per_host * host_count
    if not total_vm_estimate:
        return None

    return vmotion_count / total_vm_estimate * 100
