"""
Constants used by both the cluster and host scopes
(and by the shared cluster->host->VM traversal in traversal.py). Anything that
belongs to only one object type lives in constants_cluster.py / constants_host.py
instead.
"""

ADAPTER_KIND = "ClusterPerfRisk"
ADAPTER_NAME = "Cluster Performance Risk"

VMWARE_ADAPTER_KIND = "VMWARE"
RESOURCE_KIND_CLUSTER = "ClusterComputeResource"
RESOURCE_KIND_HOST = "HostSystem"
RESOURCE_KIND_VM = "VirtualMachine"

# Only powered-on VMs are counted (worst/P90 samples, vCPU and memory totals,
# overcommit, monster VMs). A powered-off VM keeps its last stats as "latest"
# forever, and its configured size is not using the host. A VM whose property
# is missing is not counted either.
VM_POWER_STATE_PROPERTY = "summary|runtime|powerState"
VM_POWERED_ON = "Powered On"

# A stat whose latest sample is older than this is no data (see
# suite_api.is_stale). Two 5-minute collection cycles, so one late cycle does
# not blank everything. Properties are never stale: VCF Operations stores a
# property only when it changes, so its last value is its current value.
STALE_AFTER_MINUTES = 10
# How far the collector's own clock may be ahead of VCF Operations before the
# clock-based half of the staleness check gives a false "stale".
CLOCK_SKEW_TOLERANCE_MINUTES = 5

# Adapter parameter key for the monster-VM threshold (see get_adapter_definition
# in adapter.py). Read via adapter_instance.get_identifier_value() at collect
# time -- never hardcode the threshold in adapter.py. Feeds monster VM detection
# in traversal.py, which drives both the cluster ratio metrics and the host raw
# count metric.
PARAM_MONSTER_VM_THRESHOLD_PCT = "monster_vm_threshold_pct"
DEFAULT_MONSTER_VM_THRESHOLD_PCT = 50

# Raw statkey "cpu|utilization_average" -- reused across scopes: cluster.py's
# NATIVE_STATKEY_MAP maps it to the cluster metric METRIC_CPU_THREAD_UTILIZATION
# ("highest across hosts"), cluster.py's host_cpu_imbalance_pct() uses it for the
# per-host stdev proxy, and traversal.py uses it directly for the host object's
# own HOST_METRIC_CPU_THREAD_UTILIZATION -- three different derived metrics from
# one statkey, across both object types.
CPU_UTILIZATION_STATKEY = "cpu|utilization_average"

# memory_ballooned_pct (cluster) and host_memory_ballooned_pct (host) both derive
# from these raw statkeys as (ballooned KB / host memory KB) * 100 -- no native
# percentage statkey exists for either scope.
MEMORY_BALLOON_KB_STATKEY = "mem|vmmemctl_average"
# Host memory, the denominator of ballooned %, memory overcommit and the
# memory monster VM test, is the host's DRAM (KB). On a host with memory
# tiering, mem|host_provisioned includes the NVMe tier, which VMs do not run
# in, so a % of it understates the pressure on DRAM. The DRAM tier stat is
# used when it has a value; mem|host_provisioned (also KB) otherwise, e.g. on
# versions without memory tiering stats. Neither: the memory rows are no data.
MEMORY_DRAM_CAPACITY_KB_STATKEY = "mem:DRAM|memory_tier_total_capacity"
MEMORY_TOTAL_CAPACITY_KB_STATKEY = "mem|host_provisioned"

# Monster VM detection (traversal.py): a VM counts as a CPU (or memory) monster
# VM when its vCPU count (or memory) exceeds monster_vm_threshold_pct of its
# host's total CPU cores (or memory) -- a practical proxy for "may not fit in
# one NUMA node", since NUMA topology isn't exposed via SuiteAPI. Confirmed live
# 2026-08-15 against ops.vcf.gillaspy.org: all three keys return real,
# non-property (i.e. /stats/latest-fetchable) data. mem|guest_provisioned
# mirrors mem|host_provisioned's KB convention, so no unit conversion needed
# when comparing the two. HOST_CPU_CORES_STATKEY also feeds
# HOST_METRIC_CPU_OVERCOMMIT_RATIO (host-only), so it lives here rather than in
# constants_host.py.
VM_NUM_CPU_STATKEY = "config|hardware|num_Cpu"
VM_MEMORY_KB_STATKEY = "mem|guest_provisioned"
HOST_CPU_CORES_STATKEY = "hardware|cpuInfo|num_CpuCores"

# "How Deep?" (worst = max across all VMs) / "How Broad?" (p90 across all VMs)
# pairs, computed once per cluster and once per host from the same per-VM
# samples in traversal.py, then reused as-is by both object types -- confirmed
# 2026-08-17 that the bounds table is identical for both scopes, so neither
# object type redefines its own copy of these metric keys.
METRIC_WORST_VCPU_READY = "worst_vcpu_ready_pct"
METRIC_P90_VCPU_READY = "p90_vcpu_ready_pct"
METRIC_WORST_VCPU_COSTOP = "worst_vcpu_costop_pct"
METRIC_P90_VCPU_COSTOP = "p90_vcpu_costop_pct"
# "Memory Latency" (mem|latency_average) is not monitored on this instance
# (defaultMonitored: False, confirmed absent of data) -- using memory
# contention instead (mem|20_sec_peak_host_contentionPct), which is actively
# monitored and follows the same "peak of 20s samples" convention as the
# other 3 VM-level metrics here.
METRIC_WORST_MEMORY_CONTENTION = "worst_memory_contention_pct"
METRIC_P90_MEMORY_CONTENTION = "p90_memory_contention_pct"
METRIC_WORST_DISK_LATENCY = "worst_disk_latency_ms"
METRIC_P90_DISK_LATENCY = "p90_disk_latency_ms"

# Per-VM statkeys for the worst/p90 metric pairs above, confirmed live
# 2026-08-17 against ops.vcf.gillaspy.org (real, non-null data; all
# defaultMonitored: True except memory contention, which is monitored under
# this key even though mem|latency_average -- the originally-proposed one --
# is not). Keyed by an internal sample-bucket name shared with
# VM_WORST_P90_METRICS below.
VM_LEVEL_STATKEYS = {
    "vcpu_ready": "cpu|20_sec_peak_readyPct",
    "vcpu_costop": "cpu|20_sec_peak_costopPct",
    "memory_contention": "mem|20_sec_peak_host_contentionPct",
    "disk_latency": "virtualDisk|20_sec_peak_totalLatency_average",
}

# Maps each VM_LEVEL_STATKEYS bucket to its (worst_metric_key, p90_metric_key)
# pair -- computed together in traversal.py's _worst_p90_into() from the same
# sample list.
VM_WORST_P90_METRICS = {
    "vcpu_ready": (METRIC_WORST_VCPU_READY, METRIC_P90_VCPU_READY),
    "vcpu_costop": (METRIC_WORST_VCPU_COSTOP, METRIC_P90_VCPU_COSTOP),
    "memory_contention": (METRIC_WORST_MEMORY_CONTENTION, METRIC_P90_MEMORY_CONTENTION),
    "disk_latency": (METRIC_WORST_DISK_LATENCY, METRIC_P90_DISK_LATENCY),
}

# Host-level, worst-across-hosts. Both are native pre-computed percentages
# (confirmed live 2026-08-17, defaultMonitored: True, real data) -- chosen
# over deriving from raw components because the originally-proposed
# derivation ingredients (sys|resourceMemSwapped_latest for swap%;
# net|packetsRx_summation_sum / net|packetsTx_summation_sum for the packet
# denominator) are all defaultMonitored: False on this instance and return no
# data regardless of formula correctness. net|droppedPct covers dropped
# packets only -- no monitored error-percentage statkey exists to combine in,
# so this is "dropped %", not "dropped+error %". Reused as-is on the host
# object (not rederived per-host), so these metric keys live here rather than
# in constants_cluster.py / constants_host.py.
METRIC_HOST_MEMORY_CONTENTION = "host_memory_contention_pct"
METRIC_HOST_DROPPED_PACKETS = "host_dropped_packets_pct"
HOST_MEMORY_CONTENTION_STATKEY = "mem|host_contentionPct"
HOST_DROPPED_PACKETS_STATKEY = "net|droppedPct"

# Memory zip swap, since 2.2.0: (compressed KB + swapped-out KB) / host DRAM
# KB * 100, per host; the cluster value is the worst host. Both stats return
# data on VCF Operations 9.x (confirmed on the lab 2026-10-30), unlike the
# sys|resourceMemSwapped_latest derivation tried in 2026-08 (see above).
# Host Memory Contention stays a separate metric.
METRIC_HOST_MEMORY_ZIP_SWAP = "host_memory_zip_swap_pct"

# Host CPU imbalance, since 2.2.0: running threads per running core.
#   running threads = cpu|utilization_average % x threads
#   running cores   = cpu|coreUtilization_average % x cores
# Threads are 2 x cores when the host properties config|hyperThread|available
# and |active are both "true", else the cores. 1 means one running thread per
# running core; above 1, hyper-threads share cores. The cluster value is the
# worst host. Replaces the stdev-across-hosts stand-in.
METRIC_HOST_CPU_IMBALANCE_RATIO = "host_cpu_imbalance_ratio"
HOST_CPU_CORE_UTILIZATION_STATKEY = "cpu|coreUtilization_average"
HOST_HT_AVAILABLE_PROPERTY = "config|hyperThread|available"
HOST_HT_ACTIVE_PROPERTY = "config|hyperThread|active"
MEMORY_COMPRESSED_KB_STATKEY = "mem|compressed_average"
MEMORY_SWAPOUT_KB_STATKEY = "mem|swapout_average"
