"""
Band boundaries/weights for metric keys that are reused as-is on both the
cluster_perf_risk and host_perf_risk object types (see constants_shared.py).
"""
from __future__ import annotations

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

# Each entry: green_max, yellow_max, orange_max. Anything above orange_max is red.
BAND_BOUNDS = {
    # "How Deep?"/"How Broad?" pairs -- confirmed live 2026-08-17 against
    # ops.vcf.gillaspy.org with real (non-null) VM-level data; bounds are as
    # specified, not derived from the (currently healthy, all-green) sample.
    METRIC_WORST_VCPU_READY: {"green_max": 4, "yellow_max": 8, "orange_max": 16},
    METRIC_P90_VCPU_READY: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_WORST_VCPU_COSTOP: {"green_max": 2, "yellow_max": 4, "orange_max": 8},
    METRIC_P90_VCPU_COSTOP: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    # Memory Contention substituted for the originally-proposed Memory Latency
    # (mem|latency_average is not monitored on this instance) -- see
    # constants_shared.py. Reused the same bounds since it fills the same slot
    # in the risk matrix.
    METRIC_WORST_MEMORY_CONTENTION: {"green_max": 1, "yellow_max": 2, "orange_max": 4},
    METRIC_P90_MEMORY_CONTENTION: {"green_max": 0.5, "yellow_max": 1, "orange_max": 2},
    METRIC_WORST_DISK_LATENCY: {"green_max": 40, "yellow_max": 80, "orange_max": 120},
    METRIC_P90_DISK_LATENCY: {"green_max": 20, "yellow_max": 40, "orange_max": 60},
    # Host Memory Contention substituted for the originally-proposed
    # swap%+compressed% derivation (its ingredients aren't monitored on this
    # instance -- see constants_shared.py). Reused the swap% bounds for the
    # same reason.
    METRIC_HOST_MEMORY_CONTENTION: {"green_max": 0.25, "yellow_max": 0.5, "orange_max": 1},
    # Host Dropped Packets -- net|droppedPct only (drops, not drops+errors; no
    # monitored error-percentage statkey exists to combine in -- see
    # constants_shared.py). Exact-zero green confirmed reasonable in practice:
    # live 2026-08-17 measurement was 0.0 on all 3 hosts checked.
    METRIC_HOST_DROPPED_PACKETS: {"green_max": 0, "yellow_max": 0.2, "orange_max": 0.4},
}

# Monster VM counts weighted higher -- more direct predictor of noisy-neighbor risk
WEIGHTS = {
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
}
