"""
The single shared cluster -> host -> VM traversal feeding BOTH the cluster
composite and each host's own composite -- monster VM detection, the
worst(max)/p90 vCPU ready/co-stop/memory-contention/disk-latency metrics, and
the two host-raw metrics (memory contention, dropped packets), all computed at
both cluster-pooled and per-host granularity from the same walk. Also computes
the host-only metrics (CPU thread util, memory consumed/ballooned/reservation,
CPU+memory overcommit ratio, monster VM count) per host, since we're already
there for each one.

Only powered-on VMs are counted (VM_POWER_STATE_PROPERTY): a powered-off VM's
"latest" stats are its last ones before it stopped, and its size does not use
the host.

Since 2.1.0 the stats and properties are read in bulk, once per cluster
(fetch_cluster_snapshot), instead of one GET per stat per VM.

Doing 10+ separate host->VM traversals per cluster per collection cycle (one
per metric, times two resource kinds) would multiply API calls unnecessarily
at scale -- confirmed worth avoiding: wld-cl01 alone has 7 VMs across 3 hosts,
and vcf-mgmt-cl01 has 11 across 3 hosts (2026-08-17). This is why this module
is NOT split further by object type -- cluster.py and host.py both consume its
output instead of each doing their own walk.
"""
from __future__ import annotations

import math
from typing import NamedTuple
from typing import Optional

import aria.ops.adapter_logging as logging
from aria.ops.suite_api_client import SuiteApiClient
from constants_cluster import CLUSTER_LEVEL_METRICS
from constants_cluster import HOST_LINKSPEED_PROPERTY
from constants_cluster import NATIVE_STATKEY_MAP
from constants_cluster import NETWORK_USAGE_AVERAGE_STATKEY
from constants_cluster import NUMBER_VMOTION_STATKEY
from constants_cluster import VM_COUNT_PER_HOST_STATKEY
from constants_host import HOST_CPU_CAPACITY_STATKEY
from constants_host import HOST_CPU_RESERVED_STATKEY
from constants_host import HOST_METRIC_CPU_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_CPU_RESERVATION
from constants_host import HOST_METRIC_CPU_THREAD_UTILIZATION
from constants_host import HOST_METRIC_MEMORY_BALLOONED
from constants_host import HOST_METRIC_MEMORY_CONSUMED
from constants_host import HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_MEMORY_RESERVATION
from constants_host import HOST_MEMORY_ALLOCATED_KB_STATKEY
from constants_host import HOST_MEMORY_RESERVED_PCT_STATKEY
from constants_host import HOST_MEMORY_USAGE_STATKEY
from constants_host import HOST_VCPUS_ALLOCATED_STATKEY
from constants_shared import CPU_UTILIZATION_STATKEY
from constants_shared import DEFAULT_MONSTER_VM_MEMORY_CAP_GB
from constants_shared import DEFAULT_MONSTER_VM_MEMORY_PCT
from constants_shared import DEFAULT_MONSTER_VM_THRESHOLD_PCT
from constants_shared import HOST_CPU_CORE_UTILIZATION_STATKEY
from constants_shared import HOST_CPU_CORES_STATKEY
from constants_shared import HOST_DROPPED_PACKETS_STATKEY
from constants_shared import HOST_HT_ACTIVE_PROPERTY
from constants_shared import HOST_HT_AVAILABLE_PROPERTY
from constants_shared import HOST_MEMORY_CONTENTION_STATKEY
from constants_shared import MEMORY_BALLOON_KB_STATKEY
from constants_shared import MEMORY_DRAM_CAPACITY_KB_STATKEY
from constants_shared import MEMORY_TOTAL_CAPACITY_KB_STATKEY
from constants_shared import METRIC_CPU_MONSTER_VM_SIZE_RATIO
from constants_shared import METRIC_HOST_CPU_IMBALANCE_RATIO
from constants_shared import METRIC_HOST_DROPPED_PACKETS
from constants_shared import METRIC_HOST_MEMORY_CONTENTION
from constants_shared import METRIC_HOST_MEMORY_ZIP_SWAP
from constants_shared import METRIC_MEMORY_MONSTER_VM_SIZE_RATIO
from constants_shared import MEMORY_COMPRESSED_KB_STATKEY
from constants_shared import MEMORY_SWAPOUT_KB_STATKEY
from constants_shared import RESOURCE_KIND_VM
from constants_shared import VM_POWER_STATE_PROPERTY
from constants_shared import VM_POWERED_ON
from constants_shared import VM_LEVEL_STATKEYS
from constants_shared import VM_MEMORY_KB_STATKEY
from constants_shared import VM_NUM_CPU_STATKEY
from constants_shared import VM_WORST_P90_METRICS
from suite_api import bulk_latest_properties
from suite_api import bulk_latest_stats
from suite_api import fetch_child_hosts
from suite_api import fetch_children_of_kind

logger = logging.getLogger(__name__)

KB_PER_GB = 1024 * 1024


class MonsterVmSettings(NamedTuple):
    """The adapter instance's monster VM settings (see constants_shared.py)."""

    cpu_pct: float = DEFAULT_MONSTER_VM_THRESHOLD_PCT
    memory_pct: float = DEFAULT_MONSTER_VM_MEMORY_PCT
    memory_cap_gb: float = DEFAULT_MONSTER_VM_MEMORY_CAP_GB


def _percentile(sorted_values: list[float], pct: float) -> float:
    """
    Nearest-rank percentile. Cluster VM counts here are small (single/double
    digits), so this is more transparent than an interpolated method (e.g.
    statistics.quantiles) at these sample sizes -- and unambiguous about which
    real sample "is" the p90 rather than blending two.
    """
    idx = max(0, math.ceil(pct * len(sorted_values)) - 1)
    return sorted_values[idx]


# Everything one cluster's metrics read, by object type. Read in bulk by
# fetch_cluster_snapshot(); ClusterSnapshot.stat()/prop() refuse a key not
# listed here, so a metric can never silently read a value that was not
# fetched.
CLUSTER_STATKEYS = sorted(
    {NATIVE_STATKEY_MAP[m] for m in CLUSTER_LEVEL_METRICS}
    | {VM_COUNT_PER_HOST_STATKEY, NUMBER_VMOTION_STATKEY}
)
HOST_STATKEYS = sorted(
    {v for m, v in NATIVE_STATKEY_MAP.items() if m not in CLUSTER_LEVEL_METRICS}
    | {
        HOST_CPU_CORES_STATKEY, MEMORY_DRAM_CAPACITY_KB_STATKEY,
        MEMORY_TOTAL_CAPACITY_KB_STATKEY, MEMORY_BALLOON_KB_STATKEY,
        HOST_MEMORY_CONTENTION_STATKEY, HOST_DROPPED_PACKETS_STATKEY,
        CPU_UTILIZATION_STATKEY, HOST_MEMORY_USAGE_STATKEY,
        HOST_MEMORY_RESERVED_PCT_STATKEY, HOST_CPU_RESERVED_STATKEY,
        HOST_CPU_CAPACITY_STATKEY, NETWORK_USAGE_AVERAGE_STATKEY,
        HOST_VCPUS_ALLOCATED_STATKEY, HOST_MEMORY_ALLOCATED_KB_STATKEY,
        MEMORY_COMPRESSED_KB_STATKEY, MEMORY_SWAPOUT_KB_STATKEY,
        HOST_CPU_CORE_UTILIZATION_STATKEY,
    }
)
VM_STATKEYS = sorted({VM_NUM_CPU_STATKEY, VM_MEMORY_KB_STATKEY, *VM_LEVEL_STATKEYS.values()})
HOST_PROPERTY_KEYS = [HOST_LINKSPEED_PROPERTY, HOST_HT_AVAILABLE_PROPERTY, HOST_HT_ACTIVE_PROPERTY]
VM_PROPERTY_KEYS = [VM_POWER_STATE_PROPERTY]


class ClusterSnapshot:
    """One cluster's hosts, their powered-on VMs, and the latest stats and
    properties of all of them, as read by fetch_cluster_snapshot()."""

    def __init__(
        self,
        cluster_id: str,
        hosts: list[tuple[str, str]],
        vms_by_host: dict[str, list[tuple[str, str]]],
        stats: dict[tuple[str, str], float],
        props: dict[tuple[str, str], str],
        vms_not_powered_on: int = 0,
    ) -> None:
        self.cluster_id = cluster_id
        self.hosts = hosts
        self.vms_by_host = vms_by_host
        self.stats = stats
        self.props = props
        self.vms_not_powered_on = vms_not_powered_on
        self._allowed = set(CLUSTER_STATKEYS) | set(HOST_STATKEYS) | set(VM_STATKEYS)
        self._allowed_props = set(HOST_PROPERTY_KEYS) | set(VM_PROPERTY_KEYS)

    def stat(self, resource_id: str, statkey: str) -> Optional[float]:
        if statkey not in self._allowed:
            raise KeyError(f"{statkey} is not in the bulk stat key lists (traversal.py)")
        return self.stats.get((resource_id, statkey))

    def prop(self, resource_id: str, key: str) -> Optional[str]:
        if key not in self._allowed_props:
            raise KeyError(f"{key} is not in the bulk property key lists (traversal.py)")
        return self.props.get((resource_id, key))


def fetch_cluster_snapshot(client: SuiteApiClient, cluster_id: str) -> ClusterSnapshot:
    """
    Reads everything one cluster needs. Per cluster: its hosts (one call),
    each host's VMs (one call per host -- hosts are few), then in bulk: the
    properties of all hosts and VMs, and the stats of the cluster, its hosts
    and its powered-on VMs (one request per object type and chunk). Only
    powered-on VMs' stats are read, so a powered-off VM costs nothing.
    """
    hosts = fetch_child_hosts(client, cluster_id)
    all_vms = {host_id: fetch_children_of_kind(client, host_id, RESOURCE_KIND_VM) for host_id, _ in hosts}
    vm_ids = [vm_id for vms in all_vms.values() for vm_id, _ in vms]
    host_ids = [host_id for host_id, _ in hosts]

    props: dict[tuple[str, str], str] = {}
    if host_ids:
        props.update(bulk_latest_properties(client, host_ids, HOST_PROPERTY_KEYS))
    if vm_ids:
        props.update(bulk_latest_properties(client, vm_ids, VM_PROPERTY_KEYS))

    vms_by_host = {
        host_id: [(v, n) for v, n in vms if props.get((v, VM_POWER_STATE_PROPERTY)) == VM_POWERED_ON]
        for host_id, vms in all_vms.items()
    }
    powered_on = [vm_id for vms in vms_by_host.values() for vm_id, _ in vms]

    stats: dict[tuple[str, str], float] = {}
    stats.update(bulk_latest_stats(client, [cluster_id], CLUSTER_STATKEYS))
    if host_ids:
        stats.update(bulk_latest_stats(client, host_ids, HOST_STATKEYS))
    if powered_on:
        stats.update(bulk_latest_stats(client, powered_on, VM_STATKEYS))
    return ClusterSnapshot(
        cluster_id, hosts, vms_by_host, stats, props, len(vm_ids) - len(powered_on)
    )


def host_memory_capacity_kb(snap: ClusterSnapshot, host_id: str) -> Optional[float]:
    """The host's DRAM in KB: the DRAM tier stat, else mem|host_provisioned
    (see MEMORY_DRAM_CAPACITY_KB_STATKEY). None when neither has a value."""
    dram_kb = snap.stat(host_id, MEMORY_DRAM_CAPACITY_KB_STATKEY)
    if dram_kb:
        return dram_kb
    return snap.stat(host_id, MEMORY_TOTAL_CAPACITY_KB_STATKEY)


def host_zip_swap_pct(snap: ClusterSnapshot, host_id: str, host_mem_kb: Optional[float]) -> Optional[float]:
    """(compressed + swapped-out) KB as a % of host DRAM. No data when either
    stat or the DRAM is missing -- never half a sum."""
    compressed_kb = snap.stat(host_id, MEMORY_COMPRESSED_KB_STATKEY)
    swapout_kb = snap.stat(host_id, MEMORY_SWAPOUT_KB_STATKEY)
    if compressed_kb is None or swapout_kb is None or not host_mem_kb:
        return None
    return (compressed_kb + swapout_kb) / host_mem_kb * 100


def host_cpu_imbalance_ratio(snap: ClusterSnapshot, host_id: str, host_cores: Optional[float]) -> Optional[float]:
    """Running threads per running core (see METRIC_HOST_CPU_IMBALANCE_RATIO).
    An idle host (nothing running) is 1, not imbalanced; any input missing is
    no data."""
    thread_util = snap.stat(host_id, CPU_UTILIZATION_STATKEY)
    core_util = snap.stat(host_id, HOST_CPU_CORE_UTILIZATION_STATKEY)
    if thread_util is None or core_util is None or not host_cores:
        return None
    hyperthreaded = (
        snap.prop(host_id, HOST_HT_AVAILABLE_PROPERTY) == "true"
        and snap.prop(host_id, HOST_HT_ACTIVE_PROPERTY) == "true"
    )
    threads = host_cores * 2 if hyperthreaded else host_cores
    running_threads = thread_util / 100 * threads
    running_cores = core_util / 100 * host_cores
    if not running_cores:
        return 1.0 if not running_threads else None
    return running_threads / running_cores


def monster_size_ratio(sizes: list[float], monster_size: Optional[float], vm_count: int) -> Optional[float]:
    """The largest VM's size / the host's monster size. 0 for a host with no
    powered-on VMs; no data when the monster size is unknown, or when the
    host has VMs but none of their sizes are known."""
    if not monster_size:
        return None
    if not sizes:
        return 0.0 if vm_count == 0 else None
    return max(sizes) / monster_size


def _worst(values: list[Optional[float]]) -> Optional[float]:
    known = [v for v in values if v is not None]
    return max(known) if known else None


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


def collect_cluster_and_host_metrics(
    snap: ClusterSnapshot, monster: MonsterVmSettings = MonsterVmSettings()
) -> tuple[dict[str, Optional[float]], list[tuple[str, str, dict[str, Optional[float]]]]]:
    """
    Returns (cluster_metric_values, host_records) where host_records is a
    list of (host_id, host_name, host_metric_values) tuples, one per host,
    each independently ready for its own compute_composite() call.
    """
    host_ids_and_names = snap.hosts

    host_cpu_monster_ratios: list[Optional[float]] = []
    host_memory_monster_ratios: list[Optional[float]] = []
    cluster_vm_samples: dict[str, list[float]] = {key: [] for key in VM_LEVEL_STATKEYS}
    host_memory_contention_samples = []
    host_dropped_packets_samples = []
    host_zip_swap_samples = []
    host_imbalance_samples = []
    host_records: list[tuple[str, str, dict[str, Optional[float]]]] = []

    for host_id, host_name in host_ids_and_names:
        host_cores = snap.stat(host_id, HOST_CPU_CORES_STATKEY)
        host_mem_kb = host_memory_capacity_kb(snap, host_id)

        host_mem_contention = snap.stat(host_id, HOST_MEMORY_CONTENTION_STATKEY)
        if host_mem_contention is not None:
            host_memory_contention_samples.append(host_mem_contention)
        host_dropped_pct = snap.stat(host_id, HOST_DROPPED_PACKETS_STATKEY)
        if host_dropped_pct is not None:
            host_dropped_packets_samples.append(host_dropped_pct)

        host_zip_swap = host_zip_swap_pct(snap, host_id, host_mem_kb)
        if host_zip_swap is not None:
            host_zip_swap_samples.append(host_zip_swap)

        host_imbalance = host_cpu_imbalance_ratio(snap, host_id, host_cores)
        if host_imbalance is not None:
            host_imbalance_samples.append(host_imbalance)

        host_cpu_util = snap.stat(host_id, CPU_UTILIZATION_STATKEY)
        host_mem_usage = snap.stat(host_id, HOST_MEMORY_USAGE_STATKEY)
        host_mem_reserved_pct = snap.stat(host_id, HOST_MEMORY_RESERVED_PCT_STATKEY)
        host_ballooned_kb = snap.stat(host_id, MEMORY_BALLOON_KB_STATKEY)
        host_ballooned_pct = (
            (host_ballooned_kb / host_mem_kb) * 100
            if host_ballooned_kb is not None and host_mem_kb
            else None
        )
        host_cpu_reserved = snap.stat(host_id, HOST_CPU_RESERVED_STATKEY)
        host_cpu_capacity = snap.stat(host_id, HOST_CPU_CAPACITY_STATKEY)
        host_cpu_reservation_pct = (
            (host_cpu_reserved / host_cpu_capacity) * 100
            if host_cpu_reserved is not None and host_cpu_capacity
            else None
        )

        vm_records = snap.vms_by_host.get(host_id, [])
        host_vm_samples: dict[str, list[float]] = {key: [] for key in VM_LEVEL_STATKEYS}
        host_total_vcpu = 0.0
        host_total_vmem_kb = 0.0
        vm_vcpus: list[float] = []
        vm_mem_kbs: list[float] = []

        for vm_id, _vm_name in vm_records:
            vcpu = snap.stat(vm_id, VM_NUM_CPU_STATKEY)
            if vcpu is not None:
                host_total_vcpu += vcpu
                vm_vcpus.append(vcpu)

            vmem_kb = snap.stat(vm_id, VM_MEMORY_KB_STATKEY)
            if vmem_kb is not None:
                host_total_vmem_kb += vmem_kb
                vm_mem_kbs.append(vmem_kb)

            for sample_key, statkey in VM_LEVEL_STATKEYS.items():
                value = snap.stat(vm_id, statkey)
                if value is not None:
                    cluster_vm_samples[sample_key].append(value)
                    host_vm_samples[sample_key].append(value)

        # Native allocation stats when present, else the powered-on sums.
        native_vcpu = snap.stat(host_id, HOST_VCPUS_ALLOCATED_STATKEY)
        if native_vcpu is not None:
            host_total_vcpu = native_vcpu
        native_vmem_kb = snap.stat(host_id, HOST_MEMORY_ALLOCATED_KB_STATKEY)
        if native_vmem_kb is not None:
            host_total_vmem_kb = native_vmem_kb

        cpu_monster_size = host_cores * monster.cpu_pct / 100 if host_cores else None
        memory_monster_kb = (
            min(host_mem_kb * monster.memory_pct / 100, monster.memory_cap_gb * KB_PER_GB)
            if host_mem_kb else None
        )
        host_cpu_monster = monster_size_ratio(vm_vcpus, cpu_monster_size, len(vm_records))
        host_memory_monster = monster_size_ratio(vm_mem_kbs, memory_monster_kb, len(vm_records))
        host_cpu_monster_ratios.append(host_cpu_monster)
        host_memory_monster_ratios.append(host_memory_monster)

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
            METRIC_CPU_MONSTER_VM_SIZE_RATIO: host_cpu_monster,
            METRIC_MEMORY_MONSTER_VM_SIZE_RATIO: host_memory_monster,
            METRIC_HOST_MEMORY_CONTENTION: host_mem_contention,
            METRIC_HOST_DROPPED_PACKETS: host_dropped_pct,
            METRIC_HOST_MEMORY_ZIP_SWAP: host_zip_swap,
            METRIC_HOST_CPU_IMBALANCE_RATIO: host_imbalance,
        }
        _worst_p90_into(host_metric_values, host_vm_samples)
        host_records.append((host_id, host_name, host_metric_values))

    if snap.vms_not_powered_on:
        logger.debug(f"Cluster {snap.cluster_id}: {snap.vms_not_powered_on} VMs not powered on, not counted")

    cluster_results: dict[str, Optional[float]] = {
        METRIC_CPU_MONSTER_VM_SIZE_RATIO: _worst(host_cpu_monster_ratios),
        METRIC_MEMORY_MONSTER_VM_SIZE_RATIO: _worst(host_memory_monster_ratios),
        METRIC_HOST_MEMORY_CONTENTION: (
            max(host_memory_contention_samples) if host_memory_contention_samples else None
        ),
        METRIC_HOST_DROPPED_PACKETS: (
            max(host_dropped_packets_samples) if host_dropped_packets_samples else None
        ),
        METRIC_HOST_MEMORY_ZIP_SWAP: (
            max(host_zip_swap_samples) if host_zip_swap_samples else None
        ),
        METRIC_HOST_CPU_IMBALANCE_RATIO: (
            max(host_imbalance_samples) if host_imbalance_samples else None
        ),
    }
    _worst_p90_into(cluster_results, cluster_vm_samples)

    return cluster_results, host_records
