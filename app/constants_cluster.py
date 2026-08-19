"""
Constants specific to the cluster_perf_risk object type. Metric keys reused
as-is on the host object too (worst/p90 VM metrics, host memory
contention/dropped packets) live in constants_shared.py instead.
"""
from constants_shared import CPU_UTILIZATION_STATKEY
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

OBJECT_KIND_CLUSTER_RISK = "cluster_perf_risk"
OBJECT_LABEL_CLUSTER_RISK = "vSphere Cluster Performance Risk"

IDENTIFIER_CLUSTER_VCF_ID = "cluster_vcf_id"
IDENTIFIER_CLUSTER_NAME = "cluster_name"

# Metric keys. NOTE: the matrix's two separate imbalance rows ("Highest ESXi
# CPU Imbalance" and "Cluster CPU Imbalance") are tracked as two distinct
# metrics. No per-host imbalance statkey exists on the live instance, so
# METRIC_HOST_CPU_IMBALANCE is a synthetic proxy -- population stdev of
# cpu|utilization_average across the cluster's hosts, in percentage points --
# computed in cluster.py's host_cpu_imbalance_pct(), not a real vSphere/DRS
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
# count instead (HOST_METRIC_MONSTER_VM_COUNT in constants_host.py).
METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO = "cluster_cpu_overcommit_ratio"
METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO = "cluster_memory_overcommit_ratio"
METRIC_CLUSTER_CPU_MONSTER_VM_RATIO = "cluster_cpu_monster_vm_ratio"
METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO = "cluster_memory_monster_vm_ratio"

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

# Confirmed directly against ops.vcf.gillaspy.org via
# /api/adapterkinds/VMWARE/resourcekinds/{HostSystem,ClusterComputeResource}/statkeys.
# There's no native "monster VM" statkey (confirmed absent from the live
# catalog, and NUMA topology isn't exposed via SuiteAPI) -- monster VM
# counts/ratios are computed in traversal.py as a per-VM proxy instead, in the
# same traversal that computes the worst/p90 VM metrics, so neither appears in
# this map.
NATIVE_STATKEY_MAP = {
    METRIC_CPU_THREAD_UTILIZATION: CPU_UTILIZATION_STATKEY,
    METRIC_DISK_IOPS: "disk|commandsAveraged_average",
    METRIC_CLUSTER_CPU_IMBALANCE: "clusterServices|total_imbalance",
    # ClusterComputeResource-only -- confirmed ABSENT from the HostSystem
    # catalog (2026-08-17). See constants_host.py's
    # HOST_METRIC_CPU_OVERCOMMIT_RATIO / HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
    # for the host-scope derivation.
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO: "cpu|vcpus_to_cores_allocation_ratio",
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO: "mem|virtual_to_physical_memory_allocation_ratio",
}

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
