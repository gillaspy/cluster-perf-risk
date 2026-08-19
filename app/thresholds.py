"""
Band boundaries transcribed from the vSphere Cluster Performance Risk matrix,
plus the weighted-worst-band composite scoring logic.

Kept as plain Python (not JSON) so it ships inside app/ alongside the rest of
the adapter code with no extra packaging/loading concerns.
"""
from __future__ import annotations

from constants import HOST_METRIC_CPU_OVERCOMMIT_RATIO
from constants import HOST_METRIC_CPU_RESERVATION
from constants import HOST_METRIC_CPU_THREAD_UTILIZATION
from constants import HOST_METRIC_MEMORY_BALLOONED
from constants import HOST_METRIC_MEMORY_CONSUMED
from constants import HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
from constants import HOST_METRIC_MEMORY_RESERVATION
from constants import HOST_METRIC_MONSTER_VM_COUNT
from constants import METRIC_CLUSTER_CPU_IMBALANCE
from constants import METRIC_CLUSTER_CPU_MONSTER_VM_RATIO
from constants import METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO
from constants import METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO
from constants import METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO
from constants import METRIC_CPU_THREAD_UTILIZATION
from constants import METRIC_DISK_IOPS
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

# Each entry: green_max, yellow_max, orange_max. Anything above orange_max is red.
BAND_BOUNDS = {
    METRIC_CPU_THREAD_UTILIZATION: {"green_max": 60, "yellow_max": 80, "orange_max": 90},
    METRIC_MEMORY_BALLOONED: {"green_max": 1, "yellow_max": 1.25, "orange_max": 2},
    # Re-included 2026-08-17 now that network_throughput_pct is computed from
    # a working derived formula (see constants.py) instead of the broken
    # net|usage_capacity statkey -- these are the risk matrix's original
    # bounds, which were always plausible for a real 0-100% link-utilization
    # metric; they just couldn't be trusted while the underlying value was
    # broken. Confirmed live: real values landed at 0.13%-0.93%, comfortably
    # inside this green range.
    METRIC_NETWORK_THROUGHPUT: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_DISK_IOPS: {"green_max": 25000, "yellow_max": 50000, "orange_max": 100000},
    # Synthetic proxy (population stdev of per-host CPU utilization %, computed
    # in adapter.py's _host_cpu_imbalance_pct) for the matrix's "Highest ESXi
    # CPU Imbalance" row -- no real per-host imbalance statkey exists. Bounds
    # are an unvalidated starting guess (never run against a real cluster yet);
    # calibrate once mp-test output is available.
    METRIC_HOST_CPU_IMBALANCE: {"green_max": 5, "yellow_max": 10, "orange_max": 20},
    # REVIEW: this is the real DRS statkey (clusterServices|total_imbalance),
    # cluster-level, not per-host. It's also NOT a percentage: confirmed
    # 2026-08-15 via the VCF Operations UI tooltip -- "the current balance, in
    # terms of standard deviation, for a DRS cluster. Units are thousandths."
    # (e.g. raw 12 -> 0.012). adapter.py divides by 1000 before this classifies
    # it, so bounds here are std-deviation values, not 0-100. vcf-mgmt-cl01's
    # observed 24h range was ~0.049-0.108; these bounds are still a placeholder
    # informed by that single cluster -- calibrate across more clusters before
    # trusting this metric's band.
    METRIC_CLUSTER_CPU_IMBALANCE: {"green_max": 0.05, "yellow_max": 0.08, "orange_max": 0.12},
    # vmotion_pct = summary|number_vmotion / (summary|vm_count_per_host *
    # host_count) * 100 -- see constants.py. The matrix's original bounds,
    # used as-is and explicitly UNVERIFIED against real-world vMotion
    # behavior (confirmed live 2026-08-17 that this cluster shows 0.0 -- no
    # vMotion activity to calibrate against yet).
    METRIC_VMOTION_PCT: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    # "How Deep?"/"How Broad?" pairs -- confirmed live 2026-08-17 against
    # ops.vcf.gillaspy.org with real (non-null) VM-level data; bounds are as
    # specified, not derived from the (currently healthy, all-green) sample.
    METRIC_WORST_VCPU_READY: {"green_max": 4, "yellow_max": 8, "orange_max": 16},
    METRIC_P90_VCPU_READY: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_WORST_VCPU_COSTOP: {"green_max": 2, "yellow_max": 4, "orange_max": 8},
    METRIC_P90_VCPU_COSTOP: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    # Memory Contention substituted for the originally-proposed Memory Latency
    # (mem|latency_average is not monitored on this instance) -- see
    # constants.py. Reused the same bounds since it fills the same slot in the
    # risk matrix.
    METRIC_WORST_MEMORY_CONTENTION: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_P90_MEMORY_CONTENTION: {"green_max": 0.5, "yellow_max": 1, "orange_max": 2},
    METRIC_WORST_DISK_LATENCY: {"green_max": 40, "yellow_max": 80, "orange_max": 120},
    METRIC_P90_DISK_LATENCY: {"green_max": 20, "yellow_max": 40, "orange_max": 60},
    # Host Memory Contention substituted for the originally-proposed
    # swap%+compressed% derivation (its ingredients aren't monitored on this
    # instance -- see constants.py). Reused the swap% bounds for the same reason.
    METRIC_HOST_MEMORY_CONTENTION: {"green_max": 0.25, "yellow_max": 0.5, "orange_max": 1},
    # Host Dropped Packets -- net|droppedPct only (drops, not drops+errors; no
    # monitored error-percentage statkey exists to combine in -- see
    # constants.py). Exact-zero green confirmed reasonable in practice: live
    # 2026-08-17 measurement was 0.0 on all 3 hosts checked.
    METRIC_HOST_DROPPED_PACKETS: {"green_max": 0, "yellow_max": 0.2, "orange_max": 0.4},

    # --- Cluster resource kind: 2026-08-17 net-new -------------------------
    # Both direct native ratios (ClusterComputeResource-only -- see
    # constants.py), confirmed live: vcf-mgmt-cl01 cpu=1.42 (yellow),
    # mem=0.42 (green); wld-cl01 cpu=0.5, mem=0.15 (both green).
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 3},
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 1.25, "orange_max": 1.5},
    # Replaces the old raw-count monster VM metrics at cluster scope (host
    # scope keeps a raw count -- HOST_METRIC_MONSTER_VM_COUNT below).
    METRIC_CLUSTER_CPU_MONSTER_VM_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 4},

    # --- Host resource kind (ESXi Performance Risk), 2026-08-17 -----------
    HOST_METRIC_CPU_THREAD_UTILIZATION: {"green_max": 60, "yellow_max": 80, "orange_max": 90},
    HOST_METRIC_MEMORY_CONSUMED: {"green_max": 80, "yellow_max": 90, "orange_max": 95},
    HOST_METRIC_MEMORY_BALLOONED: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    HOST_METRIC_CPU_RESERVATION: {"green_max": 40, "yellow_max": 60, "orange_max": 80},
    HOST_METRIC_MEMORY_RESERVATION: {"green_max": 40, "yellow_max": 60, "orange_max": 80},
    # DERIVED, not native -- see constants.py (cpu|vcpus_to_cores_allocation_ratio
    # / mem|virtual_to_physical_memory_allocation_ratio confirmed absent from
    # the HostSystem catalog). Confirmed live: values ranged 0.5-1.56 (cpu)
    # and 0.15-0.51 (mem) across 6 real hosts, all landing green/yellow.
    HOST_METRIC_CPU_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 2, "orange_max": 3},
    HOST_METRIC_MEMORY_OVERCOMMIT_RATIO: {"green_max": 1, "yellow_max": 1.4, "orange_max": 1.6},
    HOST_METRIC_MONSTER_VM_COUNT: {"green_max": 0, "yellow_max": 1, "orange_max": 2},
}

# Band floor scores used to compute the composite. green=0, yellow=60, orange=80, red=90
BAND_FLOORS = {"green": 0, "yellow": 60, "orange": 80, "red": 90, "unknown": 0}

# Monster VM counts weighted higher -- more direct predictor of noisy-neighbor risk
WEIGHTS = {
    METRIC_CPU_THREAD_UTILIZATION: 1.0,
    METRIC_MEMORY_BALLOONED: 1.0,
    METRIC_NETWORK_THROUGHPUT: 0.75,
    METRIC_DISK_IOPS: 0.75,
    METRIC_HOST_CPU_IMBALANCE: 0.75,
    METRIC_CLUSTER_CPU_IMBALANCE: 0.75,
    METRIC_VMOTION_PCT: 0.75,
    # "Worst" (single-VM, deep) metrics weighted like other per-host worst-case
    # signals; "p90" (broad, cluster-wide) variants weighted lower -- a starting
    # point, not calibrated against real incidents yet.
    METRIC_WORST_VCPU_READY: 1.0,
    METRIC_P90_VCPU_READY: 0.75,
    METRIC_WORST_VCPU_COSTOP: 1.0,
    METRIC_P90_VCPU_COSTOP: 0.75,
    METRIC_WORST_MEMORY_CONTENTION: 1.0,
    METRIC_P90_MEMORY_CONTENTION: 0.75,
    METRIC_WORST_DISK_LATENCY: 1.0,
    METRIC_P90_DISK_LATENCY: 0.75,
    METRIC_HOST_MEMORY_CONTENTION: 0.75,
    METRIC_HOST_DROPPED_PACKETS: 0.75,

    # Cluster: 2026-08-17 net-new. Monster VM ratios weighted higher, matching
    # the old raw-count metrics they replace.
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO: 1.0,
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO: 1.0,
    METRIC_CLUSTER_CPU_MONSTER_VM_RATIO: 1.25,
    METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO: 1.25,

    # Host resource kind: 2026-08-17. Starting weights, not calibrated against
    # real incidents yet -- same caveat as the cluster composite's weights.
    HOST_METRIC_CPU_THREAD_UTILIZATION: 1.0,
    HOST_METRIC_MEMORY_CONSUMED: 1.0,
    HOST_METRIC_MEMORY_BALLOONED: 1.0,
    HOST_METRIC_CPU_RESERVATION: 0.75,
    HOST_METRIC_MEMORY_RESERVATION: 0.75,
    HOST_METRIC_CPU_OVERCOMMIT_RATIO: 1.0,
    HOST_METRIC_MEMORY_OVERCOMMIT_RATIO: 1.0,
    HOST_METRIC_MONSTER_VM_COUNT: 1.25,
}


def classify_band(value: float | None, metric_key: str) -> str:
    """Return 'green' | 'yellow' | 'orange' | 'red' | 'unknown' for a metric value."""
    if value is None:
        return "unknown"
    bounds = BAND_BOUNDS.get(metric_key)
    if bounds is None:
        return "unknown"
    if value <= bounds["green_max"]:
        return "green"
    if value <= bounds["yellow_max"]:
        return "yellow"
    if value <= bounds["orange_max"]:
        return "orange"
    return "red"


def compute_composite(metric_values: dict[str, float | None]) -> tuple[float, str, dict[str, str]]:
    """
    metric_values: {metric_key: value_or_None}
    Returns (composite_score 0-100, composite_band, {metric_key: band})

    Weighted-worst-band: 70% weight on the single worst sub-metric's band floor,
    30% on the weighted average across all sub-metrics. This keeps one red
    sub-metric from being diluted into invisibility by several green ones.
    """
    per_metric_band: dict[str, str] = {}
    weighted_scores = []
    total_weight = 0.0

    for key, value in metric_values.items():
        if key not in BAND_BOUNDS:
            continue
        band = classify_band(value, key)
        per_metric_band[key] = band
        # Unknown metrics (null/missing collection) are excluded from the
        # composite math entirely -- otherwise their floor of 0 silently drags
        # the composite toward "green" even when real data is red/orange.
        if band == "unknown":
            continue
        weight = WEIGHTS.get(key, 1.0)
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

    if composite >= BAND_FLOORS["red"]:
        composite_band = "red"
    elif composite >= BAND_FLOORS["orange"]:
        composite_band = "orange"
    elif composite >= BAND_FLOORS["yellow"]:
        composite_band = "yellow"
    else:
        composite_band = "green"

    return composite, composite_band, per_metric_band
