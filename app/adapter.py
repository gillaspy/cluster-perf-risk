#  Cluster Performance Risk adapter
#  Self-referential: polls VCF Operations' own Suite API for native cluster/host
#  stats, classifies each into the risk-matrix bands, and republishes a composite
#  0-100 risk score + band per cluster.
import math
import statistics
import sys
from typing import Any
from typing import List
from typing import Optional

import aria.ops.adapter_logging as logging
from aria.ops.adapter_instance import AdapterInstance
from aria.ops.definition.adapter_definition import AdapterDefinition
from aria.ops.object import Identifier
from aria.ops.result import CollectResult
from aria.ops.result import EndpointResult
from aria.ops.result import TestResult
from aria.ops.suite_api_client import SuiteApiClient
from aria.ops.timer import Timer
from constants import ADAPTER_KIND
from constants import ADAPTER_NAME
from constants import BAND_PROPERTY_LABELS
from constants import CLUSTER_LEVEL_METRICS
from constants import DEFAULT_MONSTER_VM_THRESHOLD_PCT
from constants import HOST_BAND_PROPERTY_LABELS
from constants import HOST_CPU_CAPACITY_STATKEY
from constants import HOST_CPU_CORES_STATKEY
from constants import HOST_CPU_RESERVED_STATKEY
from constants import HOST_DROPPED_PACKETS_STATKEY
from constants import HOST_MEMORY_CONTENTION_STATKEY
from constants import HOST_LINKSPEED_PROPERTY
from constants import HOST_MEMORY_RESERVED_PCT_STATKEY
from constants import HOST_MEMORY_USAGE_STATKEY
from constants import HOST_METRIC_COMPOSITE_SCORE
from constants import HOST_METRIC_CPU_OVERCOMMIT_RATIO
from constants import HOST_METRIC_CPU_RESERVATION
from constants import HOST_METRIC_CPU_THREAD_UTILIZATION
from constants import HOST_METRIC_MEMORY_BALLOONED
from constants import HOST_METRIC_MEMORY_CONSUMED
from constants import HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
from constants import HOST_METRIC_MEMORY_RESERVATION
from constants import HOST_METRIC_MONSTER_VM_COUNT
from constants import HOST_PROP_COMPOSITE_BAND
from constants import IDENTIFIER_CLUSTER_NAME
from constants import IDENTIFIER_CLUSTER_VCF_ID
from constants import IDENTIFIER_HOST_CLUSTER_NAME
from constants import IDENTIFIER_HOST_NAME
from constants import IDENTIFIER_HOST_VCF_ID
from constants import MEMORY_BALLOON_KB_STATKEY
from constants import MEMORY_TOTAL_CAPACITY_KB_STATKEY
from constants import METRIC_CLUSTER_CPU_IMBALANCE
from constants import METRIC_CLUSTER_CPU_MONSTER_VM_RATIO
from constants import METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO
from constants import METRIC_COMPOSITE_SCORE
from constants import METRIC_CPU_THREAD_UTILIZATION
from constants import METRIC_HOST_CPU_IMBALANCE
from constants import METRIC_HOST_DROPPED_PACKETS
from constants import METRIC_HOST_MEMORY_CONTENTION
from constants import METRIC_MEMORY_BALLOONED
from constants import METRIC_NETWORK_THROUGHPUT
from constants import METRIC_P90_DISK_LATENCY
from constants import METRIC_P90_MEMORY_CONTENTION
from constants import METRIC_P90_VCPU_COSTOP
from constants import METRIC_P90_VCPU_READY
from constants import METRIC_VMOTION_PCT
from constants import METRIC_WORST_DISK_LATENCY
from constants import METRIC_WORST_MEMORY_CONTENTION
from constants import METRIC_WORST_VCPU_COSTOP
from constants import METRIC_WORST_VCPU_READY
from constants import NATIVE_STATKEY_MAP
from constants import NETWORK_USAGE_AVERAGE_STATKEY
from constants import NUMBER_VMOTION_STATKEY
from constants import OBJECT_KIND_CLUSTER_RISK
from constants import OBJECT_KIND_HOST_RISK
from constants import OBJECT_LABEL_CLUSTER_RISK
from constants import OBJECT_LABEL_HOST_RISK
from constants import PARAM_MONSTER_VM_THRESHOLD_PCT
from constants import PROP_COMPOSITE_BAND
from constants import RESOURCE_KIND_CLUSTER
from constants import RESOURCE_KIND_HOST
from constants import RESOURCE_KIND_VM
from constants import VM_COUNT_PER_HOST_STATKEY
from constants import VM_LEVEL_STATKEYS
from constants import VM_MEMORY_KB_STATKEY
from constants import VM_NUM_CPU_STATKEY
from constants import VM_WORST_P90_METRICS
from constants import VMWARE_ADAPTER_KIND
from thresholds import compute_composite

logger = logging.getLogger(__name__)


def get_adapter_definition() -> AdapterDefinition:
    with Timer(logger, "Get Adapter Definition"):
        definition = AdapterDefinition(ADAPTER_KIND, ADAPTER_NAME)

        definition.define_int_parameter(
            "container_memory_limit",
            label="Adapter Memory Limit (MB)",
            description="Sets the maximum amount of memory VCF Operations can "
            "allocate to the container running this adapter instance.",
            required=True,
            advanced=True,
            default=1024,
        )
        definition.define_int_parameter(
            PARAM_MONSTER_VM_THRESHOLD_PCT,
            label="Monster VM Threshold (%)",
            description="A VM counts as a CPU (or memory) monster VM when its "
            "vCPU count (or memory) exceeds this percentage of its host's "
            "total CPU cores (or memory) -- a proxy for VMs that may not fit "
            "in one NUMA node.",
            required=False,
            advanced=True,
            default=DEFAULT_MONSTER_VM_THRESHOLD_PCT,
        )

        # No credential type is defined here. This adapter is self-referential:
        # AdapterInstance.get_suite_api_client() automatically returns an
        # authenticated client for the VCF Operations instance hosting this
        # adapter, with no user-supplied host/username/password needed.

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
        # Worst/p90 VM-level metrics and the two host-level metrics below are
        # all derived in adapter.py's _collect_cluster_and_host_metrics() --
        # none have a 1:1 native statkey mapping, so none are in NATIVE_STATKEY_MAP.
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

        host_risk = definition.define_object_type(
            OBJECT_KIND_HOST_RISK, OBJECT_LABEL_HOST_RISK
        )
        host_risk.define_string_identifier(IDENTIFIER_HOST_VCF_ID, "Host VCF Resource ID")
        host_risk.define_string_identifier(
            IDENTIFIER_HOST_NAME, "Host Name", is_part_of_uniqueness=False
        )
        host_risk.define_string_identifier(
            IDENTIFIER_HOST_CLUSTER_NAME, "Cluster Name", is_part_of_uniqueness=False
        )

        # Host-only metrics.
        for metric_key, label in [
            (HOST_METRIC_CPU_THREAD_UTILIZATION, "CPU Thread Utilization Pct"),
            (HOST_METRIC_MEMORY_CONSUMED, "Memory Consumed Pct"),
            (HOST_METRIC_MEMORY_BALLOONED, "Memory Ballooned Pct"),
            (HOST_METRIC_CPU_RESERVATION, "CPU Reservation Pct"),
            (HOST_METRIC_MEMORY_RESERVATION, "Memory Reservation Pct"),
            (HOST_METRIC_CPU_OVERCOMMIT_RATIO, "CPU Overcommit Ratio"),
            (HOST_METRIC_MEMORY_OVERCOMMIT_RATIO, "Memory Overcommit Ratio"),
            (HOST_METRIC_MONSTER_VM_COUNT, "Monster VM Count"),
        ]:
            host_risk.define_metric(metric_key, label, is_kpi=True)
        # Shared VM-level inputs -- same metric keys as the cluster object,
        # computed here from just this host's own VMs. See constants.py.
        for metric_key, label in [
            (METRIC_WORST_VCPU_READY, "Worst vCPU Ready Pct"),
            (METRIC_P90_VCPU_READY, "P90 vCPU Ready Pct"),
            (METRIC_WORST_VCPU_COSTOP, "Worst vCPU Co-Stop Pct"),
            (METRIC_P90_VCPU_COSTOP, "P90 vCPU Co-Stop Pct"),
            (METRIC_WORST_MEMORY_CONTENTION, "Worst Memory Contention Pct"),
            (METRIC_P90_MEMORY_CONTENTION, "P90 Memory Contention Pct"),
            (METRIC_WORST_DISK_LATENCY, "Worst Disk Latency Ms"),
            (METRIC_P90_DISK_LATENCY, "P90 Disk Latency Ms"),
            (METRIC_HOST_MEMORY_CONTENTION, "Memory Contention Pct"),
            (METRIC_HOST_DROPPED_PACKETS, "Dropped Packets Pct"),
        ]:
            host_risk.define_metric(metric_key, label, is_kpi=True)

        host_risk.define_metric(
            HOST_METRIC_COMPOSITE_SCORE,
            "Composite Risk Score",
            is_kpi=True,
            is_key_attribute=True,
        )
        host_risk.define_string_property(
            HOST_PROP_COMPOSITE_BAND, "Composite Risk Band", is_key_attribute=True
        )
        for band_key, band_label in HOST_BAND_PROPERTY_LABELS.items():
            host_risk.define_string_property(band_key, band_label)

        logger.debug(f"Returning adapter definition: {definition.to_json()}")
        return definition


def test(adapter_instance: AdapterInstance) -> TestResult:
    with Timer(logger, "Test"):
        # get_suite_api_client() returns None when called from 'test' -- Suite
        # API calls only work inside 'collect'. There's no external host or
        # credential to validate for a self-referential adapter, so success
        # here just confirms the adapter instance itself was constructed.
        return TestResult()


def collect(adapter_instance: AdapterInstance) -> CollectResult:
    with Timer(logger, "Collection"):
        result = CollectResult()
        client = adapter_instance.get_suite_api_client()
        if client is None:
            result.with_error(
                "No Suite API client available. This adapter must run on a "
                "Cloud Proxy with access to its own VCF Operations instance."
            )
            return result

        threshold_str = adapter_instance.get_identifier_value(
            PARAM_MONSTER_VM_THRESHOLD_PCT, str(DEFAULT_MONSTER_VM_THRESHOLD_PCT)
        )
        try:
            monster_vm_threshold_pct = float(threshold_str)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid {PARAM_MONSTER_VM_THRESHOLD_PCT} value {threshold_str!r}, "
                f"falling back to default {DEFAULT_MONSTER_VM_THRESHOLD_PCT}"
            )
            monster_vm_threshold_pct = DEFAULT_MONSTER_VM_THRESHOLD_PCT

        try:
            with client:
                clusters = _fetch_resources(
                    client, RESOURCE_KIND_CLUSTER, VMWARE_ADAPTER_KIND
                )
                for cluster_id, cluster_name in clusters:
                    metric_values: dict[str, Optional[float]] = {}
                    for metric_key, statkey in NATIVE_STATKEY_MAP.items():
                        if metric_key in CLUSTER_LEVEL_METRICS:
                            metric_values[metric_key] = _latest_stat(
                                client, cluster_id, statkey
                            )
                        else:
                            metric_values[metric_key] = _highest_host_stat(
                                client, cluster_id, statkey
                            )

                    metric_values[METRIC_MEMORY_BALLOONED] = _highest_host_ballooned_pct(
                        client, cluster_id
                    )
                    metric_values[METRIC_HOST_CPU_IMBALANCE] = _host_cpu_imbalance_pct(
                        client, cluster_id
                    )
                    metric_values[METRIC_NETWORK_THROUGHPUT] = _network_throughput_pct(
                        client, cluster_id
                    )
                    metric_values[METRIC_VMOTION_PCT] = _vmotion_pct(client, cluster_id)
                    cluster_vm_metrics, host_records = _collect_cluster_and_host_metrics(
                        client, cluster_id, monster_vm_threshold_pct
                    )
                    metric_values.update(cluster_vm_metrics)

                    # clusterServices|total_imbalance comes back from the Suite API as
                    # a raw scaled integer despite its unitless appearance -- confirmed
                    # 2026-08-15 via the VCF Operations UI tooltip (see thresholds.py).
                    if metric_values.get(METRIC_CLUSTER_CPU_IMBALANCE) is not None:
                        metric_values[METRIC_CLUSTER_CPU_IMBALANCE] /= 1000

                    composite_score, composite_band, per_metric_band = compute_composite(
                        metric_values
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

                    for host_id, host_name, host_metric_values in host_records:
                        (
                            host_composite_score,
                            host_composite_band,
                            host_per_metric_band,
                        ) = compute_composite(host_metric_values)

                        host_obj = result.object(
                            ADAPTER_KIND,
                            OBJECT_KIND_HOST_RISK,
                            f"{host_name} - Perf Risk",
                            identifiers=[
                                Identifier(IDENTIFIER_HOST_VCF_ID, host_id),
                                Identifier(
                                    IDENTIFIER_HOST_NAME,
                                    host_name,
                                    is_part_of_uniqueness=False,
                                ),
                                Identifier(
                                    IDENTIFIER_HOST_CLUSTER_NAME,
                                    cluster_name,
                                    is_part_of_uniqueness=False,
                                ),
                            ],
                        )

                        for metric_key, value in host_metric_values.items():
                            if value is not None:
                                host_obj.with_metric(metric_key, value)
                            band = host_per_metric_band.get(metric_key, "unknown")
                            host_obj.with_property(f"band_{metric_key}", band)

                        host_obj.with_metric(HOST_METRIC_COMPOSITE_SCORE, host_composite_score)
                        host_obj.with_property(HOST_PROP_COMPOSITE_BAND, host_composite_band)

        except Exception as e:
            logger.error("Unexpected collection error")
            logger.exception(e)
            result.with_error(f"Unexpected collection error: {e!r}")

        logger.debug(f"Returning collection result {result.get_json()}")
        return result


def get_endpoints(adapter_instance: AdapterInstance) -> EndpointResult:
    with Timer(logger, "Get Endpoints"):
        # No external HTTPS endpoints beyond VCF Operations itself, which does
        # not need certificate handling here.
        return EndpointResult()


# --- Suite API helpers --------------------------------------------------
#
# NOTE: query_for_resources() (a convenience method on SuiteApiClient) discards
# the internal resource UUID needed for subsequent stats/relationship calls,
# so these helpers call the Suite API directly instead.


def _fetch_resources(
    client: SuiteApiClient, resource_kind: str, adapter_kind: str
) -> list[tuple[str, str]]:
    """Returns a list of (resource_id, resource_name) tuples."""
    response = client.paged_post(
        "/api/resources/query",
        "resourceList",
        json={"resourceKind": [resource_kind], "adapterKind": [adapter_kind]},
    )
    return [
        (entry["identifier"], entry["resourceKey"]["name"])
        for entry in response.get("resourceList", [])
    ]


def _latest_stat(client: SuiteApiClient, resource_id: str, statkey: str) -> Optional[float]:
    """
    We only ever request a single statKey per call, so whatever comes back is
    the value we asked for -- even when VCF Operations auto-aggregates an
    instanced metric and renames the key with an instance prefix (e.g.
    disk:Aggregate of all instances|commandsAveraged_average instead of
    disk|commandsAveraged_average). Matching the returned key exactly against
    the requested key silently dropped those aggregated values.
    """
    with client.get(
        f"/api/resources/{resource_id}/stats/latest",
        params={"statKey": [statkey]},
    ) as response:
        if not response.ok:
            return None
        body: dict[str, Any] = response.json()
        for entry in body.get("values", []):
            for stat in entry.get("stat-list", {}).get("stat", []):
                data = stat.get("data", [])
                if data:
                    return data[-1]
    return None


def _get_property(client: SuiteApiClient, resource_id: str, property_name: str) -> Optional[str]:
    """
    Resource PROPERTIES (config, inventory metadata) are a different endpoint
    and response shape from stats -- /api/resources/{id}/properties, not
    /stats/latest. Values come back as strings regardless of underlying type
    (e.g. "10000.0" for a numeric linkspeed), so callers must cast.
    """
    with client.get(f"/api/resources/{resource_id}/properties") as response:
        if not response.ok:
            return None
        body: dict[str, Any] = response.json()
        for prop in body.get("property", []):
            if prop.get("name") == property_name:
                return prop.get("value")
    return None


def _fetch_children_of_kind(
    client: SuiteApiClient, resource_id: str, resource_kind: str
) -> list[tuple[str, str]]:
    """Returns (resource_id, resource_name) tuples of resource_id's direct children of the given kind."""
    with client.get(
        f"/api/resources/{resource_id}/relationships",
        params={"relationshipType": "CHILD"},
    ) as response:
        if not response.ok:
            return []
        body = response.json()
        return [
            (entry["identifier"], entry["resourceKey"]["name"])
            for entry in body.get("resourceList", [])
            if entry.get("resourceKey", {}).get("resourceKindKey") == resource_kind
        ]


def _fetch_child_hosts(client: SuiteApiClient, cluster_id: str) -> list[tuple[str, str]]:
    """Returns (host_id, host_name) tuples of the cluster's direct HostSystem children."""
    return _fetch_children_of_kind(client, cluster_id, RESOURCE_KIND_HOST)


def _highest_host_ballooned_pct(client: SuiteApiClient, cluster_id: str) -> Optional[float]:
    """
    memory_ballooned_pct has no native percentage statkey. Computed per host as
    (ballooned KB / total host memory KB) * 100, then the max across hosts in
    the cluster is returned (matching the matrix's "Highest ESXi ..." framing).
    """
    host_ids = _fetch_child_hosts(client, cluster_id)

    ratios = []
    for host_id, _host_name in host_ids:
        ballooned_kb = _latest_stat(client, host_id, MEMORY_BALLOON_KB_STATKEY)
        total_kb = _latest_stat(client, host_id, MEMORY_TOTAL_CAPACITY_KB_STATKEY)
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
    host_ids = _fetch_child_hosts(client, cluster_id)
    cpu_statkey = NATIVE_STATKEY_MAP[METRIC_CPU_THREAD_UTILIZATION]

    values = [
        v
        for v in (_latest_stat(client, host_id, cpu_statkey) for host_id, _host_name in host_ids)
        if v is not None
    ]
    return statistics.pstdev(values) if len(values) >= 2 else None


def _network_throughput_pct(client: SuiteApiClient, cluster_id: str) -> Optional[float]:
    """
    net|usage_capacity (previously used here) is NOT usable despite catalog
    metadata claiming unit "%" -- see constants.py for the full story. This
    derives the real percentage instead: per host, (net|usage_average KBps
    converted to Mbps) / (config|network|linkspeed Mbps, a resource PROPERTY
    fetched via a different endpoint than stats) * 100, then max across the
    cluster's hosts -- the matrix's established "highest across hosts" pattern.
    """
    host_ids = _fetch_child_hosts(client, cluster_id)

    ratios = []
    for host_id, _host_name in host_ids:
        usage_kbps = _latest_stat(client, host_id, NETWORK_USAGE_AVERAGE_STATKEY)
        linkspeed_str = _get_property(client, host_id, HOST_LINKSPEED_PROPERTY)
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
    interval. See constants.py -- bounds here are unverified against
    real-world vMotion behavior.
    """
    host_ids = _fetch_child_hosts(client, cluster_id)
    host_count = len(host_ids)
    if not host_count:
        return None

    vm_count_per_host = _latest_stat(client, cluster_id, VM_COUNT_PER_HOST_STATKEY)
    vmotion_count = _latest_stat(client, cluster_id, NUMBER_VMOTION_STATKEY)
    if vm_count_per_host is None or vmotion_count is None:
        return None

    total_vm_estimate = vm_count_per_host * host_count
    if not total_vm_estimate:
        return None

    return vmotion_count / total_vm_estimate * 100


def _percentile(sorted_values: list[float], pct: float) -> float:
    """
    Nearest-rank percentile. Cluster VM counts here are small (single/double
    digits), so this is more transparent than an interpolated method (e.g.
    statistics.quantiles) at these sample sizes -- and unambiguous about which
    real sample "is" the p90 rather than blending two.
    """
    idx = max(0, math.ceil(pct * len(sorted_values)) - 1)
    return sorted_values[idx]


def _worst_p90_into(
    target: dict[str, Optional[float]], samples_by_key: dict[str, list[float]]
) -> None:
    """Computes worst/p90 for each VM_WORST_P90_METRICS bucket and writes the
    (worst_metric, p90_metric) pair into target. Shared by both the
    cluster-wide and per-host aggregation passes below so the two stay
    consistent."""
    for sample_key, (worst_metric, p90_metric) in VM_WORST_P90_METRICS.items():
        samples = sorted(samples_by_key[sample_key])
        if samples:
            target[worst_metric] = samples[-1]
            target[p90_metric] = _percentile(samples, 0.9)
        else:
            target[worst_metric] = None
            target[p90_metric] = None


def _collect_cluster_and_host_metrics(
    client: SuiteApiClient, cluster_id: str, monster_vm_threshold_pct: float
) -> tuple[dict[str, Optional[float]], list[tuple[str, str, dict[str, Optional[float]]]]]:
    """
    Single shared cluster -> host -> VM traversal feeding BOTH the cluster
    composite and each host's own composite -- monster VM detection, the
    worst(max)/p90 vCPU ready/co-stop/memory-contention/disk-latency metrics,
    and the two host-raw metrics (memory contention, dropped packets), all
    computed at both cluster-pooled and per-host granularity from the same
    walk. Also computes the host-only metrics (CPU thread util, memory
    consumed/ballooned/reservation, CPU+memory overcommit ratio, monster VM
    count) per host, since we're already there for each one.

    Doing 10+ separate host->VM traversals per cluster per collection cycle
    (one per metric, times two resource kinds) would multiply API calls
    unnecessarily at scale -- confirmed worth avoiding: wld-cl01 alone has 7
    VMs across 3 hosts, and vcf-mgmt-cl01 has 11 across 3 hosts (2026-08-17).

    host_cpu_overcommit_ratio / host_memory_overcommit_ratio are DERIVED (sum
    of this host's VMs' vCPU or memory / this host's cores or memory) rather
    than native -- cpu|vcpus_to_cores_allocation_ratio and
    mem|virtual_to_physical_memory_allocation_ratio only exist on
    ClusterComputeResource, confirmed absent from the HostSystem catalog
    (2026-08-17) -- see constants.py. This reuses the exact per-VM vCPU/memory
    values already being fetched for monster VM detection, no extra API calls.

    Returns (cluster_metric_values, host_records) where host_records is a
    list of (host_id, host_name, host_metric_values) tuples, one per host,
    each independently ready for its own compute_composite() call.
    """
    host_ids_and_names = _fetch_child_hosts(client, cluster_id)

    cpu_monster_count = 0
    memory_monster_count = 0
    saw_host_capacity_data = False
    cluster_vm_samples: dict[str, list[float]] = {key: [] for key in VM_LEVEL_STATKEYS}
    host_memory_contention_samples = []
    host_dropped_packets_samples = []
    host_records: list[tuple[str, str, dict[str, Optional[float]]]] = []

    for host_id, host_name in host_ids_and_names:
        host_cores = _latest_stat(client, host_id, HOST_CPU_CORES_STATKEY)
        host_mem_kb = _latest_stat(client, host_id, MEMORY_TOTAL_CAPACITY_KB_STATKEY)
        host_has_capacity_data = bool(host_cores or host_mem_kb)
        if host_has_capacity_data:
            saw_host_capacity_data = True

        host_mem_contention = _latest_stat(client, host_id, HOST_MEMORY_CONTENTION_STATKEY)
        if host_mem_contention is not None:
            host_memory_contention_samples.append(host_mem_contention)
        host_dropped_pct = _latest_stat(client, host_id, HOST_DROPPED_PACKETS_STATKEY)
        if host_dropped_pct is not None:
            host_dropped_packets_samples.append(host_dropped_pct)

        host_cpu_util = _latest_stat(client, host_id, NATIVE_STATKEY_MAP[METRIC_CPU_THREAD_UTILIZATION])
        host_mem_usage = _latest_stat(client, host_id, HOST_MEMORY_USAGE_STATKEY)
        host_mem_reserved_pct = _latest_stat(client, host_id, HOST_MEMORY_RESERVED_PCT_STATKEY)
        host_ballooned_kb = _latest_stat(client, host_id, MEMORY_BALLOON_KB_STATKEY)
        host_ballooned_pct = (
            (host_ballooned_kb / host_mem_kb) * 100
            if host_ballooned_kb is not None and host_mem_kb
            else None
        )
        host_cpu_reserved = _latest_stat(client, host_id, HOST_CPU_RESERVED_STATKEY)
        host_cpu_capacity = _latest_stat(client, host_id, HOST_CPU_CAPACITY_STATKEY)
        host_cpu_reservation_pct = (
            (host_cpu_reserved / host_cpu_capacity) * 100
            if host_cpu_reserved is not None and host_cpu_capacity
            else None
        )

        vm_records = _fetch_children_of_kind(client, host_id, RESOURCE_KIND_VM)
        host_vm_samples: dict[str, list[float]] = {key: [] for key in VM_LEVEL_STATKEYS}
        host_monster_vm_ids: set[str] = set()
        host_total_vcpu = 0.0
        host_total_vmem_kb = 0.0

        for vm_id, _vm_name in vm_records:
            vcpu = _latest_stat(client, vm_id, VM_NUM_CPU_STATKEY)
            if vcpu is not None:
                host_total_vcpu += vcpu
                if host_cores and (vcpu / host_cores) * 100 > monster_vm_threshold_pct:
                    cpu_monster_count += 1
                    host_monster_vm_ids.add(vm_id)

            vmem_kb = _latest_stat(client, vm_id, VM_MEMORY_KB_STATKEY)
            if vmem_kb is not None:
                host_total_vmem_kb += vmem_kb
                if host_mem_kb and (vmem_kb / host_mem_kb) * 100 > monster_vm_threshold_pct:
                    memory_monster_count += 1
                    host_monster_vm_ids.add(vm_id)

            for sample_key, statkey in VM_LEVEL_STATKEYS.items():
                value = _latest_stat(client, vm_id, statkey)
                if value is not None:
                    cluster_vm_samples[sample_key].append(value)
                    host_vm_samples[sample_key].append(value)

        host_metric_values: dict[str, Optional[float]] = {
            HOST_METRIC_CPU_THREAD_UTILIZATION: host_cpu_util,
            HOST_METRIC_MEMORY_CONSUMED: host_mem_usage,
            HOST_METRIC_MEMORY_BALLOONED: host_ballooned_pct,
            HOST_METRIC_CPU_RESERVATION: host_cpu_reservation_pct,
            HOST_METRIC_MEMORY_RESERVATION: host_mem_reserved_pct,
            HOST_METRIC_CPU_OVERCOMMIT_RATIO: (
                (host_total_vcpu / host_cores) if host_cores else None
            ),
            HOST_METRIC_MEMORY_OVERCOMMIT_RATIO: (
                (host_total_vmem_kb / host_mem_kb) if host_mem_kb else None
            ),
            HOST_METRIC_MONSTER_VM_COUNT: (
                len(host_monster_vm_ids) if host_has_capacity_data else None
            ),
            METRIC_HOST_MEMORY_CONTENTION: host_mem_contention,
            METRIC_HOST_DROPPED_PACKETS: host_dropped_pct,
        }
        _worst_p90_into(host_metric_values, host_vm_samples)
        host_records.append((host_id, host_name, host_metric_values))

    host_count = len(host_ids_and_names)
    cluster_results: dict[str, Optional[float]] = {
        METRIC_CLUSTER_CPU_MONSTER_VM_RATIO: (
            cpu_monster_count / host_count
            if saw_host_capacity_data and host_count
            else None
        ),
        METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO: (
            memory_monster_count / host_count
            if saw_host_capacity_data and host_count
            else None
        ),
        METRIC_HOST_MEMORY_CONTENTION: (
            max(host_memory_contention_samples) if host_memory_contention_samples else None
        ),
        METRIC_HOST_DROPPED_PACKETS: (
            max(host_dropped_packets_samples) if host_dropped_packets_samples else None
        ),
    }
    _worst_p90_into(cluster_results, cluster_vm_samples)

    return cluster_results, host_records


def _highest_host_stat(
    client: SuiteApiClient, cluster_id: str, statkey: str
) -> Optional[float]:
    host_ids = _fetch_child_hosts(client, cluster_id)

    values = [
        v
        for v in (_latest_stat(client, host_id, statkey) for host_id, _host_name in host_ids)
        if v is not None
    ]
    return max(values) if values else None


# Main entry point -- unchanged from the mp-init template
def main(argv: List[str]) -> None:
    logging.setup_logging("adapter.log")
    logging.rotate()
    logger.info(f"Running adapter code with arguments: {argv}")
    if len(argv) != 3:
        logger.error("Arguments must be <method> <inputfile> <ouputfile>")
        sys.exit(1)

    method = argv[0]
    try:
        if method == "test":
            test(AdapterInstance.from_input()).send_results()
        elif method == "endpoint_urls":
            get_endpoints(AdapterInstance.from_input()).send_results()
        elif method == "collect":
            collect(AdapterInstance.from_input()).send_results()
        elif method == "adapter_definition":
            result = get_adapter_definition()
            if type(result) is AdapterDefinition:
                result.send_results()
            else:
                logger.info(
                    "get_adapter_definition method did not return an AdapterDefinition"
                )
                sys.exit(1)
        else:
            logger.error(f"Command {method} not found")
            sys.exit(1)
    finally:
        logger.info(Timer.graph())
        sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
