"""
The single shared cluster -> host -> VM traversal feeding BOTH the cluster
composite and each host's own composite -- monster VM detection, the
worst(max)/p90 vCPU ready/co-stop/memory-contention/disk-latency metrics, and
the two host-raw metrics (memory contention, dropped packets), all computed at
both cluster-pooled and per-host granularity from the same walk. Also computes
the host-only metrics (CPU thread util, memory consumed/ballooned/reservation,
CPU+memory overcommit ratio, monster VM count) per host, since we're already
there for each one.

Doing 10+ separate host->VM traversals per cluster per collection cycle (one
per metric, times two resource kinds) would multiply API calls unnecessarily
at scale -- confirmed worth avoiding: wld-cl01 alone has 7 VMs across 3 hosts,
and vcf-mgmt-cl01 has 11 across 3 hosts (2026-08-17). This is why this module
is NOT split further by object type -- cluster.py and host.py both consume its
output instead of each doing their own walk.
"""
from __future__ import annotations

import math
from typing import Optional

from aria.ops.suite_api_client import SuiteApiClient
from constants_cluster import METRIC_CLUSTER_CPU_MONSTER_VM_RATIO
from constants_cluster import METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO
from constants_host import HOST_CPU_CAPACITY_STATKEY
from constants_host import HOST_CPU_RESERVED_STATKEY
from constants_host import HOST_METRIC_CPU_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_CPU_RESERVATION
from constants_host import HOST_METRIC_CPU_THREAD_UTILIZATION
from constants_host import HOST_METRIC_MEMORY_BALLOONED
from constants_host import HOST_METRIC_MEMORY_CONSUMED
from constants_host import HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_MEMORY_RESERVATION
from constants_host import HOST_METRIC_MONSTER_VM_COUNT
from constants_host import HOST_MEMORY_RESERVED_PCT_STATKEY
from constants_host import HOST_MEMORY_USAGE_STATKEY
from constants_shared import CPU_UTILIZATION_STATKEY
from constants_shared import HOST_CPU_CORES_STATKEY
from constants_shared import HOST_DROPPED_PACKETS_STATKEY
from constants_shared import HOST_MEMORY_CONTENTION_STATKEY
from constants_shared import MEMORY_BALLOON_KB_STATKEY
from constants_shared import MEMORY_TOTAL_CAPACITY_KB_STATKEY
from constants_shared import METRIC_HOST_DROPPED_PACKETS
from constants_shared import METRIC_HOST_MEMORY_CONTENTION
from constants_shared import RESOURCE_KIND_VM
from constants_shared import VM_LEVEL_STATKEYS
from constants_shared import VM_MEMORY_KB_STATKEY
from constants_shared import VM_NUM_CPU_STATKEY
from constants_shared import VM_WORST_P90_METRICS
from suite_api import fetch_child_hosts
from suite_api import fetch_children_of_kind
from suite_api import latest_stat


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


def collect_cluster_and_host_metrics(
    client: SuiteApiClient, cluster_id: str, monster_vm_threshold_pct: float
) -> tuple[dict[str, Optional[float]], list[tuple[str, str, dict[str, Optional[float]]]]]:
    """
    Returns (cluster_metric_values, host_records) where host_records is a
    list of (host_id, host_name, host_metric_values) tuples, one per host,
    each independently ready for its own compute_composite() call.
    """
    host_ids_and_names = fetch_child_hosts(client, cluster_id)

    cpu_monster_count = 0
    memory_monster_count = 0
    saw_host_capacity_data = False
    cluster_vm_samples: dict[str, list[float]] = {key: [] for key in VM_LEVEL_STATKEYS}
    host_memory_contention_samples = []
    host_dropped_packets_samples = []
    host_records: list[tuple[str, str, dict[str, Optional[float]]]] = []

    for host_id, host_name in host_ids_and_names:
        host_cores = latest_stat(client, host_id, HOST_CPU_CORES_STATKEY)
        host_mem_kb = latest_stat(client, host_id, MEMORY_TOTAL_CAPACITY_KB_STATKEY)
        host_has_capacity_data = bool(host_cores or host_mem_kb)
        if host_has_capacity_data:
            saw_host_capacity_data = True

        host_mem_contention = latest_stat(client, host_id, HOST_MEMORY_CONTENTION_STATKEY)
        if host_mem_contention is not None:
            host_memory_contention_samples.append(host_mem_contention)
        host_dropped_pct = latest_stat(client, host_id, HOST_DROPPED_PACKETS_STATKEY)
        if host_dropped_pct is not None:
            host_dropped_packets_samples.append(host_dropped_pct)

        host_cpu_util = latest_stat(client, host_id, CPU_UTILIZATION_STATKEY)
        host_mem_usage = latest_stat(client, host_id, HOST_MEMORY_USAGE_STATKEY)
        host_mem_reserved_pct = latest_stat(client, host_id, HOST_MEMORY_RESERVED_PCT_STATKEY)
        host_ballooned_kb = latest_stat(client, host_id, MEMORY_BALLOON_KB_STATKEY)
        host_ballooned_pct = (
            (host_ballooned_kb / host_mem_kb) * 100
            if host_ballooned_kb is not None and host_mem_kb
            else None
        )
        host_cpu_reserved = latest_stat(client, host_id, HOST_CPU_RESERVED_STATKEY)
        host_cpu_capacity = latest_stat(client, host_id, HOST_CPU_CAPACITY_STATKEY)
        host_cpu_reservation_pct = (
            (host_cpu_reserved / host_cpu_capacity) * 100
            if host_cpu_reserved is not None and host_cpu_capacity
            else None
        )

        vm_records = fetch_children_of_kind(client, host_id, RESOURCE_KIND_VM)
        host_vm_samples: dict[str, list[float]] = {key: [] for key in VM_LEVEL_STATKEYS}
        host_monster_vm_ids: set[str] = set()
        host_total_vcpu = 0.0
        host_total_vmem_kb = 0.0

        for vm_id, _vm_name in vm_records:
            vcpu = latest_stat(client, vm_id, VM_NUM_CPU_STATKEY)
            if vcpu is not None:
                host_total_vcpu += vcpu
                if host_cores and (vcpu / host_cores) * 100 > monster_vm_threshold_pct:
                    cpu_monster_count += 1
                    host_monster_vm_ids.add(vm_id)

            vmem_kb = latest_stat(client, vm_id, VM_MEMORY_KB_STATKEY)
            if vmem_kb is not None:
                host_total_vmem_kb += vmem_kb
                if host_mem_kb and (vmem_kb / host_mem_kb) * 100 > monster_vm_threshold_pct:
                    memory_monster_count += 1
                    host_monster_vm_ids.add(vm_id)

            for sample_key, statkey in VM_LEVEL_STATKEYS.items():
                value = latest_stat(client, vm_id, statkey)
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
