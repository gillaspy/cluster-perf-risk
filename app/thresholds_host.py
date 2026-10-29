"""
Band boundaries/weights for host-scope-only metric keys. Metric keys
shared with the cluster object live in thresholds_shared.py instead.
"""
from __future__ import annotations

from constants_host import HOST_METRIC_CPU_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_CPU_RESERVATION
from constants_host import HOST_METRIC_CPU_THREAD_UTILIZATION
from constants_host import HOST_METRIC_MEMORY_BALLOONED
from constants_host import HOST_METRIC_MEMORY_CONSUMED
from constants_host import HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_MEMORY_RESERVATION
from constants_host import HOST_METRIC_MONSTER_VM_COUNT

# Each entry: green_max, yellow_max, orange_max. Anything above orange_max is red.
# 2026-08-17 net-new, alongside the host scope.
BAND_BOUNDS = {
    HOST_METRIC_CPU_THREAD_UTILIZATION: {"green_max": 60, "yellow_max": 80, "orange_max": 90},
    HOST_METRIC_MEMORY_CONSUMED: {"green_max": 80, "yellow_max": 90, "orange_max": 95},
    HOST_METRIC_MEMORY_BALLOONED: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    # 2.1.0: 40/60/80 -> 10/40/60.
    HOST_METRIC_CPU_RESERVATION: {"green_max": 10, "yellow_max": 40, "orange_max": 60},
    HOST_METRIC_MEMORY_RESERVATION: {"green_max": 10, "yellow_max": 40, "orange_max": 60},
    # DERIVED, not native -- see constants_host.py
    # (cpu|vcpus_to_cores_allocation_ratio /
    # mem|virtual_to_physical_memory_allocation_ratio confirmed absent from
    # the HostSystem catalog). Confirmed live: values ranged 0.5-1.56 (cpu)
    # and 0.15-0.51 (mem) across 6 real hosts, all landing green/yellow.
    HOST_METRIC_CPU_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 3},
    # 2.1.0: orange_max 1.6 -> 1.8.
    HOST_METRIC_MEMORY_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 1.4, "orange_max": 1.8},
    HOST_METRIC_MONSTER_VM_COUNT: {"green_max": 0, "yellow_max": 1, "orange_max": 2},
}

# Starting weights, not calibrated against real incidents yet -- same caveat
# as the cluster composite's weights (thresholds_cluster.py).
WEIGHTS = {
    HOST_METRIC_CPU_THREAD_UTILIZATION: 1.0,
    HOST_METRIC_MEMORY_CONSUMED: 1.0,
    HOST_METRIC_MEMORY_BALLOONED: 1.0,
    HOST_METRIC_CPU_RESERVATION: 0.75,
    HOST_METRIC_MEMORY_RESERVATION: 0.75,
    HOST_METRIC_CPU_OVERCOMMIT_RATIO: 1.0,
    HOST_METRIC_MEMORY_OVERCOMMIT_RATIO: 1.0,
    HOST_METRIC_MONSTER_VM_COUNT: 1.25,
}
