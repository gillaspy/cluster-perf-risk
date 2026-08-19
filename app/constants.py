ADAPTER_KIND = "ClusterPerfRisk"
ADAPTER_NAME = "Cluster Performance Risk"

OBJECT_KIND_CLUSTER_RISK = "cluster_perf_risk"
OBJECT_LABEL_CLUSTER_RISK = "vSphere Cluster Performance Risk"

IDENTIFIER_CLUSTER_VCF_ID = "cluster_vcf_id"
IDENTIFIER_CLUSTER_NAME = "cluster_name"

OBJECT_KIND_HOST_RISK = "host_perf_risk"
OBJECT_LABEL_HOST_RISK = "ESXi Performance Risk"

IDENTIFIER_HOST_VCF_ID = "host_vcf_id"
IDENTIFIER_HOST_NAME = "host_name"
# Non-unique context identifier linking a host object back to its cluster's
# display name -- mirrors IDENTIFIER_CLUSTER_NAME's is_part_of_uniqueness=False.
IDENTIFIER_HOST_CLUSTER_NAME = "cluster_name"

# Metric keys. NOTE: the matrix's two separate imbalance rows ("Highest ESXi
# CPU Imbalance" and "Cluster CPU Imbalance") are tracked as two distinct
# metrics. No per-host imbalance statkey exists on the live instance, so
# METRIC_HOST_CPU_IMBALANCE is a synthetic proxy -- population stdev of
# cpu|utilization_average across the cluster's hosts, in percentage points --
# computed in adapter.py's _host_cpu_imbalance_pct(), not a real vSphere/DRS
# statkey. METRIC_CLUSTER_CPU_IMBALANCE remains the real DRS statkey
# (clusterServices|total_imbalance).
METRIC_CPU_THREAD_UTILIZATION = "cpu_thread_utilization_pct"
METRIC_MEMORY_BALLOONED = "memory_ballooned_pct"
METRIC_NETWORK_THROUGHPUT = "network_throughput_pct"
METRIC_DISK_IOPS = "disk_iops"
METRIC_HOST_CPU_IMBALANCE = "highest_host_cpu_imbalance_pct"
METRIC_CLUSTER_CPU_IMBALANCE = "cluster_cpu_imbalance"
METRIC_VMOTION_PCT = "vmotion_pct"

# 2026-08-17: replaced the cluster-scope raw monster-VM counts with
# ratio-to-host-count metrics (see METRIC_CLUSTER_CPU_MONSTER_VM_RATIO /
# METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO below) -- host scope keeps a raw
# count instead (HOST_METRIC_MONSTER_VM_COUNT).
METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO = "cluster_cpu_overcommit_ratio"
METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO = "cluster_memory_overcommit_ratio"
METRIC_CLUSTER_CPU_MONSTER_VM_RATIO = "cluster_cpu_monster_vm_ratio"
METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO = "cluster_memory_monster_vm_ratio"

# "How Deep?" (worst = max across all VMs in the cluster) / "How Broad?" (p90
# across all VMs) pairs -- same underlying per-VM statkey, different
# aggregation. See VM_LEVEL_STATKEYS / VM_WORST_P90_METRICS below.
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

# Host-level, worst-across-hosts. Both use native pre-computed percentage
# statkeys rather than deriving from raw components -- see NATIVE_STATKEY_MAP
# comment below for why (the originally-proposed derivation ingredients
# aren't monitored on this instance).
METRIC_HOST_MEMORY_CONTENTION = "host_memory_contention_pct"
METRIC_HOST_DROPPED_PACKETS = "host_dropped_packets_pct"

METRIC_COMPOSITE_SCORE = "composite_risk_score"

# Sub-metrics that are already cluster-level (no per-host "highest" rollup needed)
CLUSTER_LEVEL_METRICS = {
    METRIC_CLUSTER_CPU_IMBALANCE,
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO,
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO,
}

PROP_COMPOSITE_BAND = "composite_risk_band"

BAND_PROPERTY_LABELS = {
    f"band_{METRIC_CPU_THREAD_UTILIZATION}": "CPU Thread Utilization Band",
    f"band_{METRIC_MEMORY_BALLOONED}": "Memory Ballooned Band",
    f"band_{METRIC_NETWORK_THROUGHPUT}": "Network Throughput Band",
    f"band_{METRIC_DISK_IOPS}": "Disk IOPS Band",
    f"band_{METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO}": "Cluster CPU Overcommit Ratio Band",
    f"band_{METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO}": "Cluster Memory Overcommit Ratio Band",
    f"band_{METRIC_CLUSTER_CPU_MONSTER_VM_RATIO}": "Cluster CPU Monster VM Ratio Band",
    f"band_{METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO}": "Cluster Memory Monster VM Ratio Band",
    f"band_{METRIC_HOST_CPU_IMBALANCE}": "Highest ESXi CPU Imbalance Band",
    f"band_{METRIC_CLUSTER_CPU_IMBALANCE}": "Cluster CPU Imbalance Band",
    f"band_{METRIC_VMOTION_PCT}": "vMotion Pct Band",
    f"band_{METRIC_WORST_VCPU_READY}": "Worst vCPU Ready Band",
    f"band_{METRIC_P90_VCPU_READY}": "P90 vCPU Ready Band",
    f"band_{METRIC_WORST_VCPU_COSTOP}": "Worst vCPU Co-Stop Band",
    f"band_{METRIC_P90_VCPU_COSTOP}": "P90 vCPU Co-Stop Band",
    f"band_{METRIC_WORST_MEMORY_CONTENTION}": "Worst Memory Contention Band",
    f"band_{METRIC_P90_MEMORY_CONTENTION}": "P90 Memory Contention Band",
    f"band_{METRIC_WORST_DISK_LATENCY}": "Worst Disk Latency Band",
    f"band_{METRIC_P90_DISK_LATENCY}": "P90 Disk Latency Band",
    f"band_{METRIC_HOST_MEMORY_CONTENTION}": "Host Memory Contention Band",
    f"band_{METRIC_HOST_DROPPED_PACKETS}": "Host Dropped Packets Band",
}

# --- Host resource kind (ESXi Performance Risk) ---------------------------
#
# Own composite score/band, own BAND_BOUNDS/WEIGHTS entries (see
# thresholds.py) -- independently tunable from the cluster composite even
# where numbers currently coincide.
#
# The 6 "shared VM-level inputs" (worst/p90 vCPU ready, worst/p90 vCPU
# co-stop, worst/p90 memory contention, worst/p90 disk latency, host memory
# contention, host dropped packets) are NOT redefined here -- confirmed
# 2026-08-17 that the bounds table is identical for both cluster and host
# scope, so the host object reuses METRIC_WORST_VCPU_READY etc. directly,
# computed from just this host's own VMs instead of the whole cluster's.
#
# host_cpu_overcommit_ratio / host_memory_overcommit_ratio are DERIVED, not
# native: cpu|vcpus_to_cores_allocation_ratio and
# mem|virtual_to_physical_memory_allocation_ratio (used at cluster scope)
# were confirmed ABSENT from the HostSystem statkey catalog entirely
# (2026-08-17) -- they only exist on ClusterComputeResource, despite the
# original handoff describing them as "same statkey, this host's own value".
# Derived instead as (sum of this host's VMs' vCPU or memory) / (this host's
# cores or memory), mirroring the cluster stat's own documented definition
# ("vCPUs allocated to powered on VMs / physical cores") using the exact
# per-VM data already collected in the shared VM pass.
HOST_METRIC_CPU_THREAD_UTILIZATION = "host_cpu_thread_utilization_pct"
HOST_METRIC_MEMORY_CONSUMED = "host_memory_consumed_pct"
HOST_METRIC_MEMORY_BALLOONED = "host_memory_ballooned_pct"
HOST_METRIC_CPU_RESERVATION = "host_cpu_reservation_pct"
HOST_METRIC_MEMORY_RESERVATION = "host_memory_reservation_pct"
HOST_METRIC_CPU_OVERCOMMIT_RATIO = "host_cpu_overcommit_ratio"
HOST_METRIC_MEMORY_OVERCOMMIT_RATIO = "host_memory_overcommit_ratio"
HOST_METRIC_MONSTER_VM_COUNT = "host_monster_vm_count"

# OPEN ITEM, not implemented: host-level CPU Imbalance. No native
# imbalance/deviation/variance-style HostSystem statkey exists (confirmed by
# a full catalog search 2026-08-17 -- nothing beyond an unrelated boolean
# DRS-eligibility flag). A derived "this host's utilization / cluster
# average" is possible but the handoff didn't specify aggregation window or
# whether powered-off hosts should be included -- needs a formula answer,
# not more statkey digging, same as vMotion % below.

HOST_PROP_COMPOSITE_BAND = "host_composite_risk_band"
HOST_METRIC_COMPOSITE_SCORE = "host_composite_risk_score"

HOST_BAND_PROPERTY_LABELS = {
    f"band_{HOST_METRIC_CPU_THREAD_UTILIZATION}": "CPU Thread Utilization Band",
    f"band_{HOST_METRIC_MEMORY_CONSUMED}": "Memory Consumed Band",
    f"band_{HOST_METRIC_MEMORY_BALLOONED}": "Memory Ballooned Band",
    f"band_{HOST_METRIC_CPU_RESERVATION}": "CPU Reservation Band",
    f"band_{HOST_METRIC_MEMORY_RESERVATION}": "Memory Reservation Band",
    f"band_{HOST_METRIC_CPU_OVERCOMMIT_RATIO}": "CPU Overcommit Ratio Band",
    f"band_{HOST_METRIC_MEMORY_OVERCOMMIT_RATIO}": "Memory Overcommit Ratio Band",
    f"band_{HOST_METRIC_MONSTER_VM_COUNT}": "Monster VM Count Band",
    # Shared VM-level inputs, reusing the cluster-scope metric keys (see above).
    f"band_{METRIC_WORST_VCPU_READY}": "Worst vCPU Ready Band",
    f"band_{METRIC_P90_VCPU_READY}": "P90 vCPU Ready Band",
    f"band_{METRIC_WORST_VCPU_COSTOP}": "Worst vCPU Co-Stop Band",
    f"band_{METRIC_P90_VCPU_COSTOP}": "P90 vCPU Co-Stop Band",
    f"band_{METRIC_WORST_MEMORY_CONTENTION}": "Worst Memory Contention Band",
    f"band_{METRIC_P90_MEMORY_CONTENTION}": "P90 Memory Contention Band",
    f"band_{METRIC_WORST_DISK_LATENCY}": "Worst Disk Latency Band",
    f"band_{METRIC_P90_DISK_LATENCY}": "P90 Disk Latency Band",
    f"band_{METRIC_HOST_MEMORY_CONTENTION}": "Host Memory Contention Band",
    f"band_{METRIC_HOST_DROPPED_PACKETS}": "Host Dropped Packets Band",
}

# Confirmed directly against ops.vcf.gillaspy.org via
# /api/adapterkinds/VMWARE/resourcekinds/{HostSystem,ClusterComputeResource}/statkeys.
# There's no native "monster VM" statkey (confirmed absent from the live
# catalog, and NUMA topology isn't exposed via SuiteAPI) -- monster VM
# counts/ratios are computed in adapter.py's _collect_vm_and_host_metrics()
# as a per-VM proxy instead, in the same traversal that computes the
# worst/p90 VM metrics below, so neither appears in this map.
NATIVE_STATKEY_MAP = {
    METRIC_CPU_THREAD_UTILIZATION: "cpu|utilization_average",
    METRIC_DISK_IOPS: "disk|commandsAveraged_average",
    METRIC_CLUSTER_CPU_IMBALANCE: "clusterServices|total_imbalance",
    # ClusterComputeResource-only -- confirmed ABSENT from the HostSystem
    # catalog (2026-08-17). See HOST_METRIC_CPU_OVERCOMMIT_RATIO /
    # HOST_METRIC_MEMORY_OVERCOMMIT_RATIO above for the host-scope derivation.
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO: "cpu|vcpus_to_cores_allocation_ratio",
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO: "mem|virtual_to_physical_memory_allocation_ratio",
}

# memory_ballooned_pct has no native percentage statkey -- it's computed as
# (ballooned KB / total host memory KB) * 100 from these two raw statkeys.
MEMORY_BALLOON_KB_STATKEY = "mem|vmmemctl_average"
MEMORY_TOTAL_CAPACITY_KB_STATKEY = "mem|host_provisioned"

# network_throughput_pct: net|usage_capacity is NOT usable despite catalog
# metadata claiming unit "%" -- confirmed 2026-08-15 via both a direct API
# call (~612K/~408K raw values) AND the VCF Operations UI itself showing the
# same large numbers for the same metric. A real metadata/reality mismatch in
# VMware's own catalog, not an adapter bug -- see the git history around that
# date for the full investigation (a /10000 guess was tried and falsified
# too). Replaced 2026-08-17 with a derived calculation using two host-level
# inputs: net|usage_average (a real stat, KBps) and config|network|linkspeed
# (a RESOURCE PROPERTY, not a stat -- fetched via a different endpoint,
# /api/resources/{id}/properties, not /stats/latest; comes back as a string,
# e.g. "10000.0" for 10Gbps). Computed per host as
# (usage_average_KBps * 8 / 1000) / linkspeed_Mbps * 100, then max across the
# cluster's hosts -- same "highest across hosts" pattern as other host-raw
# metrics. Confirmed live: real values landed at 0.13%-0.93% across 6 hosts,
# comfortably within a genuine 0-100% range (unlike net|usage_capacity's
# impossible >100% results).
NETWORK_USAGE_AVERAGE_STATKEY = "net|usage_average"
HOST_LINKSPEED_PROPERTY = "config|network|linkspeed"

# vmotion_pct: no native statkey combines these into a ready percentage.
# summary|vm_count_per_host (cluster-level) is an AVERAGE, not a cluster VM
# total -- confirmed live: vm_count_per_host * host_count reproduced the
# cluster's real VM count exactly (11.0 for vcf-mgmt-cl01, 7.0 for wld-cl01),
# so it's used as the total-VM-count estimator. summary|number_vmotion is a
# raw event count for the current collection interval. Bounds (0-1/1-2/2-4/4-8)
# are the risk matrix's original values, unverified against real-world
# vMotion behavior -- expected to need tuning once real collection data with
# nonzero vMotion activity is available.
VM_COUNT_PER_HOST_STATKEY = "summary|vm_count_per_host"
NUMBER_VMOTION_STATKEY = "summary|number_vmotion"

# Monster VM detection: a VM counts as a CPU (or memory) monster VM when its
# vCPU count (or memory) exceeds monster_vm_threshold_pct of its host's total
# CPU cores (or memory) -- a practical proxy for "may not fit in one NUMA
# node", since NUMA topology isn't exposed via SuiteAPI. Confirmed live
# 2026-08-15 against ops.vcf.gillaspy.org: all three keys return real,
# non-property (i.e. /stats/latest-fetchable) data. mem|guest_provisioned
# mirrors mem|host_provisioned's KB convention, so no unit conversion needed
# when comparing the two.
VM_NUM_CPU_STATKEY = "config|hardware|num_Cpu"
VM_MEMORY_KB_STATKEY = "mem|guest_provisioned"
HOST_CPU_CORES_STATKEY = "hardware|cpuInfo|num_CpuCores"

# Adapter parameter key for the monster-VM threshold (see get_adapter_definition
# in adapter.py). Read via adapter_instance.get_identifier_value() at collect
# time -- never hardcode the threshold in adapter.py.
PARAM_MONSTER_VM_THRESHOLD_PCT = "monster_vm_threshold_pct"
DEFAULT_MONSTER_VM_THRESHOLD_PCT = 50

# Per-VM statkeys for the worst/p90 metric pairs, confirmed live 2026-08-17
# against ops.vcf.gillaspy.org (real, non-null data; all defaultMonitored: True
# except memory contention, which is monitored under this key even though
# mem|latency_average -- the originally-proposed one -- is not). Keyed by an
# internal sample-bucket name shared with VM_WORST_P90_METRICS below.
VM_LEVEL_STATKEYS = {
    "vcpu_ready": "cpu|20_sec_peak_readyPct",
    "vcpu_costop": "cpu|20_sec_peak_costopPct",
    "memory_contention": "mem|20_sec_peak_host_contentionPct",
    "disk_latency": "virtualDisk|20_sec_peak_totalLatency_average",
}

# Maps each VM_LEVEL_STATKEYS bucket to its (worst_metric_key, p90_metric_key)
# pair -- computed together in adapter.py's _collect_vm_and_host_metrics()
# from the same sample list.
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
# so this is "dropped %", not "dropped+error %".
HOST_MEMORY_CONTENTION_STATKEY = "mem|host_contentionPct"
HOST_DROPPED_PACKETS_STATKEY = "net|droppedPct"

# Host-object-only statkeys, confirmed live 2026-08-17 (defaultMonitored:
# True, real data) against ops.vcf.gillaspy.org.
HOST_MEMORY_USAGE_STATKEY = "mem|usage_average"  # already a %, direct
HOST_CPU_RESERVED_STATKEY = "cpu|reservedCapacity_average"  # MHz
HOST_CPU_CAPACITY_STATKEY = "cpu|capacity_provisioned"  # MHz
HOST_MEMORY_RESERVED_PCT_STATKEY = "mem|reservedCapacityPct"  # already a %, direct

VMWARE_ADAPTER_KIND = "VMWARE"
RESOURCE_KIND_CLUSTER = "ClusterComputeResource"
RESOURCE_KIND_HOST = "HostSystem"
RESOURCE_KIND_VM = "VirtualMachine"
