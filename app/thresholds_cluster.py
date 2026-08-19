"""
Band boundaries/weights for cluster_perf_risk-only metric keys, transcribed
from the vSphere Cluster Performance Risk matrix. Metric keys shared with the
host object live in thresholds_shared.py instead.
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

# Each entry: green_max, yellow_max, orange_max. Anything above orange_max is red.
BAND_BOUNDS = {
    METRIC_CPU_THREAD_UTILIZATION: {"green_max": 60, "yellow_max": 80, "orange_max": 90},
    METRIC_MEMORY_BALLOONED: {"green_max": 1, "yellow_max": 1.25, "orange_max": 2},
    # Re-included 2026-08-17 now that network_throughput_pct is computed from
    # a working derived formula (see constants_cluster.py) instead of the
    # broken net|usage_capacity statkey -- these are the risk matrix's
    # original bounds, which were always plausible for a real 0-100%
    # link-utilization metric; they just couldn't be trusted while the
    # underlying value was broken. Confirmed live: real values landed at
    # 0.13%-0.93%, comfortably inside this green range.
    METRIC_NETWORK_THROUGHPUT: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_DISK_IOPS: {"green_max": 25000, "yellow_max": 50000, "orange_max": 100000},
    # Synthetic proxy (population stdev of per-host CPU utilization %, computed
    # in cluster.py's host_cpu_imbalance_pct) for the matrix's "Highest ESXi
    # CPU Imbalance" row -- no real per-host imbalance statkey exists. Bounds
    # are an unvalidated starting guess (never run against a real cluster yet);
    # calibrate once mp-test output is available.
    METRIC_HOST_CPU_IMBALANCE: {"green_max": 5, "yellow_max": 10, "orange_max": 20},
    # REVIEW: this is the real DRS statkey (clusterServices|total_imbalance),
    # cluster-level, not per-host. It's also NOT a percentage: confirmed
    # 2026-08-15 via the VCF Operations UI tooltip -- "the current balance, in
    # terms of standard deviation, for a DRS cluster. Units are thousandths."
    # (e.g. raw 12 -> 0.012). cluster.py divides by 1000 before this classifies
    # it, so bounds here are std-deviation values, not 0-100. vcf-mgmt-cl01's
    # observed 24h range was ~0.049-0.108; these bounds are still a placeholder
    # informed by that single cluster -- calibrate across more clusters before
    # trusting this metric's band.
    METRIC_CLUSTER_CPU_IMBALANCE: {"green_max": 0.05, "yellow_max": 0.08, "orange_max": 0.12},
    # vmotion_pct = summary|number_vmotion / (summary|vm_count_per_host *
    # host_count) * 100 -- see constants_cluster.py. The matrix's original
    # bounds, used as-is and explicitly UNVERIFIED against real-world vMotion
    # behavior (confirmed live 2026-08-17 that this cluster shows 0.0 -- no
    # vMotion activity to calibrate against yet).
    METRIC_VMOTION_PCT: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    # Both direct native ratios (ClusterComputeResource-only -- see
    # constants_cluster.py), confirmed live: vcf-mgmt-cl01 cpu=1.42 (yellow),
    # mem=0.42 (green); wld-cl01 cpu=0.5, mem=0.15 (both green).
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 3},
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 1.25, "orange_max": 1.5},
    # Replaces the old raw-count monster VM metrics at cluster scope (host
    # scope keeps a raw count -- HOST_METRIC_MONSTER_VM_COUNT in
    # thresholds_host.py).
    METRIC_CLUSTER_CPU_MONSTER_VM_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
}

WEIGHTS = {
    METRIC_CPU_THREAD_UTILIZATION: 1.0,
    METRIC_MEMORY_BALLOONED: 1.0,
    METRIC_NETWORK_THROUGHPUT: 0.75,
    METRIC_DISK_IOPS: 0.75,
    METRIC_HOST_CPU_IMBALANCE: 0.75,
    METRIC_CLUSTER_CPU_IMBALANCE: 0.75,
    METRIC_VMOTION_PCT: 0.75,
    # 2026-08-17 net-new. Monster VM ratios weighted higher, matching the old
    # raw-count metrics they replace.
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO: 1.0,
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO: 1.0,
    METRIC_CLUSTER_CPU_MONSTER_VM_RATIO: 1.25,
    METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO: 1.25,
}
