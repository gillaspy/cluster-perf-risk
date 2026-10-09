"""
Native-object projection (v2.0.0: the only output of this pack).

The risk values are written as write-only attributes onto the existing VMWARE
ClusterComputeResource and HostSystem objects, under a dedicated root so
nothing in the base tree can be overwritten:

    Performance Risk|<Group>|<Label>

Guardrails (enforced by tests/test_native_projection.py):
  * every projected key starts with NATIVE_ROOT + "|"
  * no projected key equals a native statkey/property key
  * no projected key starts with the vCommunity MP's "vCommunity|" root
  * the pack defines and emits no objects of its own (no ClusterPerfRisk kinds)
"""
from __future__ import annotations

from constants_cluster import METRIC_CLUSTER_CPU_IMBALANCE
from constants_cluster import METRIC_CLUSTER_CPU_MONSTER_VM_RATIO
from constants_cluster import METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO
from constants_cluster import METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO
from constants_cluster import METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO
from constants_cluster import METRIC_CPU_THREAD_UTILIZATION
from constants_cluster import METRIC_DISK_IOPS
from constants_cluster import METRIC_HOST_CPU_IMBALANCE
from constants_cluster import METRIC_MEMORY_BALLOONED
from constants_cluster import METRIC_NETWORK_THROUGHPUT
from constants_cluster import METRIC_VMOTION_PCT
from constants_host import HOST_METRIC_CPU_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_CPU_RESERVATION
from constants_host import HOST_METRIC_CPU_THREAD_UTILIZATION
from constants_host import HOST_METRIC_MEMORY_BALLOONED
from constants_host import HOST_METRIC_MEMORY_CONSUMED
from constants_host import HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_MEMORY_RESERVATION
from constants_host import HOST_METRIC_MONSTER_VM_COUNT
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

NATIVE_ROOT = "Performance Risk"
FORBIDDEN_ROOTS = ("vCommunity|",)  # other MPs' namespaces -- never write there

# Shared VM-level inputs (same metric keys on cluster and host objects).
_SHARED = {
    METRIC_WORST_VCPU_READY: ("Contention", "Worst vCPU Ready Pct"),
    METRIC_P90_VCPU_READY: ("Contention", "P90 vCPU Ready Pct"),
    METRIC_WORST_VCPU_COSTOP: ("Contention", "Worst vCPU Co-Stop Pct"),
    METRIC_P90_VCPU_COSTOP: ("Contention", "P90 vCPU Co-Stop Pct"),
    METRIC_WORST_MEMORY_CONTENTION: ("Contention", "Worst VM Memory Contention Pct"),
    METRIC_P90_MEMORY_CONTENTION: ("Contention", "P90 VM Memory Contention Pct"),
    METRIC_HOST_MEMORY_CONTENTION: ("Contention", "Host Memory Contention Pct"),
    METRIC_WORST_DISK_LATENCY: ("Storage", "Worst Disk Latency Ms"),
    METRIC_P90_DISK_LATENCY: ("Storage", "P90 Disk Latency Ms"),
    METRIC_HOST_DROPPED_PACKETS: ("Network", "Host Dropped Packets Pct"),
}

# metric key -> (group, label)
CLUSTER_PROJECTION = {
    **_SHARED,
    METRIC_CPU_THREAD_UTILIZATION: ("CPU", "Max Host Thread Utilization Pct"),
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO: ("CPU", "Overcommit Ratio"),
    METRIC_CLUSTER_CPU_MONSTER_VM_RATIO: ("CPU", "Monster VM Ratio"),
    METRIC_HOST_CPU_IMBALANCE: ("Balance", "Host CPU Imbalance Pct"),
    METRIC_CLUSTER_CPU_IMBALANCE: ("Balance", "DRS CPU Imbalance"),
    METRIC_VMOTION_PCT: ("Balance", "vMotion Pct"),
    METRIC_MEMORY_BALLOONED: ("Memory", "Max Host Ballooned Pct"),
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO: ("Memory", "Overcommit Ratio"),
    METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO: ("Memory", "Monster VM Ratio"),
    METRIC_NETWORK_THROUGHPUT: ("Network", "Max Host Throughput Pct"),
    METRIC_DISK_IOPS: ("Storage", "Max Host Disk IOPS"),
}

HOST_PROJECTION = {
    **_SHARED,
    HOST_METRIC_CPU_THREAD_UTILIZATION: ("CPU", "Thread Utilization Pct"),
    HOST_METRIC_CPU_RESERVATION: ("CPU", "Reservation Pct"),
    HOST_METRIC_CPU_OVERCOMMIT_RATIO: ("CPU", "Overcommit Ratio"),
    HOST_METRIC_MONSTER_VM_COUNT: ("CPU", "Monster VM Count"),
    HOST_METRIC_MEMORY_CONSUMED: ("Memory", "Consumed Pct"),
    HOST_METRIC_MEMORY_BALLOONED: ("Memory", "Ballooned Pct"),
    HOST_METRIC_MEMORY_RESERVATION: ("Memory", "Reservation Pct"),
    HOST_METRIC_MEMORY_OVERCOMMIT_RATIO: ("Memory", "Overcommit Ratio"),
}


COMPOSITE_SCORE_ATTR = f"{NATIVE_ROOT}|Composite|Risk Score"
COMPOSITE_BAND_ATTR = f"{NATIVE_ROOT}|Composite|Risk Band"


def metric_attr(group: str, label: str) -> str:
    return f"{NATIVE_ROOT}|{group}|{label}"


def band_attr(group: str, label: str) -> str:
    return f"{NATIVE_ROOT}|{group}|{label} Band"
