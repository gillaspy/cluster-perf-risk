"""
Everything specific to the cluster_perf_risk (vSphere Cluster Performance
Risk) object type: its adapter definition, its own derived metrics (ballooned
%, CPU imbalance proxy, network throughput %, vMotion %), and building its
CollectResult object. Metrics/records shared with the host object come from
traversal.py instead.
"""
import statistics
from typing import Optional

from aria.ops.definition.adapter_definition import AdapterDefinition
from aria.ops.object import Identifier
from aria.ops.object import Object
from aria.ops.result import CollectResult
from aria.ops.suite_api_client import SuiteApiClient
from constants_cluster import BAND_PROPERTY_LABELS
from constants_cluster import CLUSTER_LEVEL_METRICS
from constants_cluster import HOST_LINKSPEED_PROPERTY
from constants_cluster import IDENTIFIER_CLUSTER_NAME
from constants_cluster import IDENTIFIER_CLUSTER_VCF_ID
from constants_cluster import METRIC_CLUSTER_CPU_IMBALANCE
from constants_cluster import METRIC_CLUSTER_CPU_MONSTER_VM_RATIO
from constants_cluster import METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO
from constants_cluster import METRIC_COMPOSITE_SCORE
from constants_cluster import METRIC_CPU_THREAD_UTILIZATION
from constants_cluster import METRIC_HOST_CPU_IMBALANCE
from constants_cluster import METRIC_MEMORY_BALLOONED
from constants_cluster import METRIC_NETWORK_THROUGHPUT
from constants_cluster import METRIC_VMOTION_PCT
from constants_cluster import NATIVE_STATKEY_MAP
from constants_cluster import NETWORK_USAGE_AVERAGE_STATKEY
from constants_cluster import NUMBER_VMOTION_STATKEY
from constants_cluster import OBJECT_KIND_CLUSTER_RISK
from constants_cluster import OBJECT_LABEL_CLUSTER_RISK
from constants_cluster import PROP_COMPOSITE_BAND
from constants_cluster import VM_COUNT_PER_HOST_STATKEY
from constants_shared import ADAPTER_KIND
from constants_shared import MEMORY_BALLOON_KB_STATKEY
from constants_shared import MEMORY_TOTAL_CAPACITY_KB_STATKEY
from constants_shared import METRIC_HOST_DROPPED_PACKETS
from constants_shared import METRIC_HOST_MEMORY_CONTENTION
from constants_shared import METRIC_P90_DISK_LATENCY
from constants_shared import METRIC_P90_MEMORY_CONTENTION
from constants_shared import METRIC_P90_VCPU_COSTOP
from constants_shared import METRIC_P90_VCPU_READY
from constants_shared import METRIC_WORST_DISK_LATENCY
from constants_shared import METRIC_WORST_MEMORY_CONTENTION
from constants_shared import METRIC_WORST_VCPU_COSTOP
from constants_shared import METRIC_WORST_VCPU_READY
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


def define_object_type(definition: AdapterDefinition) -> None:
    cluster_risk = definition.define_object_type(
        OBJECT_KIND_CLUSTER_RISK, OBJECT_LABEL_CLUSTER_RISK
    )
    cluster_risk.define_string_identifier(
        IDENTIFIER_CLUSTER_VCF_ID, "Cluster VCF Resource ID"
    )
    cluster_risk.define_string_identifier(
        IDENTIFIER_CLUSTER_NAME,
        "Cluster Name",
        is_part_of_uniqueness=False,
    )

    for metric_key in NATIVE_STATKEY_MAP:
        cluster_risk.define_metric(metric_key, metric_key.replace("_", " ").title(), is_kpi=True)
    # memory_ballooned_pct, highest_host_cpu_imbalance_pct, and the monster
    # VM ratios are all derived (no native statkey for any of them), so
    # they're not in NATIVE_STATKEY_MAP -- define them separately.
    cluster_risk.define_metric(
        METRIC_MEMORY_BALLOONED, "Memory Ballooned Pct", is_kpi=True
    )
    cluster_risk.define_metric(
        METRIC_NETWORK_THROUGHPUT, "Network Throughput Pct", is_kpi=True
    )
    cluster_risk.define_metric(
        METRIC_HOST_CPU_IMBALANCE, "Highest ESXi CPU Imbalance Pct", is_kpi=True
    )
    cluster_risk.define_metric(
        METRIC_CLUSTER_CPU_MONSTER_VM_RATIO, "Cluster CPU Monster VM Ratio", is_kpi=True
    )
    cluster_risk.define_metric(
        METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO, "Cluster Memory Monster VM Ratio", is_kpi=True
    )
    cluster_risk.define_metric(
        METRIC_VMOTION_PCT, "vMotion Pct", is_kpi=True
    )
    # Worst/p90 VM-level metrics and the two host-level metrics below are all
    # derived in traversal.py -- none have a 1:1 native statkey mapping, so
    # none are in NATIVE_STATKEY_MAP.
    for metric_key, label in [
        (METRIC_WORST_VCPU_READY, "Worst vCPU Ready Pct"),
        (METRIC_P90_VCPU_READY, "P90 vCPU Ready Pct"),
        (METRIC_WORST_VCPU_COSTOP, "Worst vCPU Co-Stop Pct"),
        (METRIC_P90_VCPU_COSTOP, "P90 vCPU Co-Stop Pct"),
        (METRIC_WORST_MEMORY_CONTENTION, "Worst Memory Contention Pct"),
        (METRIC_P90_MEMORY_CONTENTION, "P90 Memory Contention Pct"),
        (METRIC_WORST_DISK_LATENCY, "Worst Disk Latency Ms"),
        (METRIC_P90_DISK_LATENCY, "P90 Disk Latency Ms"),
        (METRIC_HOST_MEMORY_CONTENTION, "Host Memory Contention Pct"),
        (METRIC_HOST_DROPPED_PACKETS, "Host Dropped Packets Pct"),
    ]:
        cluster_risk.define_metric(metric_key, label, is_kpi=True)

    cluster_risk.define_metric(
        METRIC_COMPOSITE_SCORE,
        "Composite Risk Score",
        is_kpi=True,
        is_key_attribute=True,
    )
    cluster_risk.define_string_property(
        PROP_COMPOSITE_BAND, "Composite Risk Band", is_key_attribute=True
    )
    for band_key, band_label in BAND_PROPERTY_LABELS.items():
        cluster_risk.define_string_property(band_key, band_label)


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


def build_object(
    result: CollectResult,
    cluster_id: str,
    cluster_name: str,
    metric_values: dict[str, Optional[float]],
) -> Object:
    composite_score, composite_band, per_metric_band = scoring.compute_composite(
        metric_values, BAND_BOUNDS, WEIGHTS
    )

    obj = result.object(
        ADAPTER_KIND,
        OBJECT_KIND_CLUSTER_RISK,
        f"{cluster_name} - Perf Risk",
        identifiers=[
            Identifier(IDENTIFIER_CLUSTER_VCF_ID, cluster_id),
            Identifier(
                IDENTIFIER_CLUSTER_NAME,
                cluster_name,
                is_part_of_uniqueness=False,
            ),
        ],
    )

    for metric_key, value in metric_values.items():
        if value is not None:
            obj.with_metric(metric_key, value)
        band = per_metric_band.get(metric_key, "unknown")
        obj.with_property(f"band_{metric_key}", band)

    obj.with_metric(METRIC_COMPOSITE_SCORE, composite_score)
    obj.with_property(PROP_COMPOSITE_BAND, composite_band)

    return obj


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
