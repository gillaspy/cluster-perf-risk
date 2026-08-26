"""
Constants used by both the cluster_perf_risk and host_perf_risk object types
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
# from these two raw statkeys as (ballooned KB / total host memory KB) * 100 --
# no native percentage statkey exists for either scope.
MEMORY_BALLOON_KB_STATKEY = "mem|vmmemctl_average"
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
