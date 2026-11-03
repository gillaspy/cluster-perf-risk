"""
Constants specific to the cluster scope (projected onto ClusterComputeResource). Metric keys reused
as-is on the host object too (worst/p90 VM metrics, host memory
contention/dropped packets) live in constants_shared.py instead.
"""
from constants_shared import CPU_UTILIZATION_STATKEY
from constants_shared import METRIC_CPU_MONSTER_VM_SIZE_RATIO
from constants_shared import METRIC_HOST_CPU_IMBALANCE_RATIO
from constants_shared import METRIC_HOST_DROPPED_PACKETS
from constants_shared import METRIC_HOST_MEMORY_CONTENTION
from constants_shared import METRIC_HOST_MEMORY_ZIP_SWAP
from constants_shared import METRIC_MEMORY_MONSTER_VM_SIZE_RATIO
from constants_shared import METRIC_P90_DISK_LATENCY
from constants_shared import METRIC_P90_MEMORY_CONTENTION
from constants_shared import METRIC_P90_VCPU_COSTOP
from constants_shared import METRIC_P90_VCPU_READY
from constants_shared import METRIC_WORST_DISK_LATENCY
from constants_shared import METRIC_WORST_MEMORY_CONTENTION
from constants_shared import METRIC_WORST_VCPU_COSTOP
from constants_shared import METRIC_WORST_VCPU_READY



# Metric keys. NOTE: the matrix's two separate imbalance rows ("Highest ESXi
# CPU Imbalance" and "Cluster CPU Imbalance") are tracked as two distinct
# metrics. Since 2.2.0 the first is METRIC_HOST_CPU_IMBALANCE_RATIO
# (constants_shared.py, running threads per running core, worst host); the
# stdev-across-hosts stand-in it replaces is gone. METRIC_CLUSTER_CPU_IMBALANCE
# remains the real DRS statkey (clusterServices|total_imbalance).
METRIC_CPU_THREAD_UTILIZATION = "cpu_thread_utilization_pct"
METRIC_MEMORY_BALLOONED = "memory_ballooned_pct"
METRIC_NETWORK_THROUGHPUT = "network_throughput_pct"
METRIC_DISK_IOPS = "disk_iops"
METRIC_CLUSTER_CPU_IMBALANCE = "cluster_cpu_imbalance"
METRIC_VMOTION_PCT = "vmotion_pct"

METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO = "cluster_cpu_overcommit_ratio"
METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO = "cluster_memory_overcommit_ratio"


# Sub-metrics that are already cluster-level (no per-host "highest" rollup needed)
CLUSTER_LEVEL_METRICS = {
    METRIC_CLUSTER_CPU_IMBALANCE,
    METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO,
    METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO,
}


BAND_PROPERTY_LABELS = {
    f"band_{METRIC_CPU_THREAD_UTILIZATION}": "CPU Thread Utilization Band",
    f"band_{METRIC_MEMORY_BALLOONED}": "Memory Ballooned Band",
    f"band_{METRIC_NETWORK_THROUGHPUT}": "Network Throughput Band",
    f"band_{METRIC_DISK_IOPS}": "Disk IOPS Band",
    f"band_{METRIC_CLUSTER_CPU_OVERCOMMIT_RATIO}": "Cluster CPU Overcommit Ratio Band",
    f"band_{METRIC_CLUSTER_MEMORY_OVERCOMMIT_RATIO}": "Cluster Memory Overcommit Ratio Band",
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
    f"band_{METRIC_HOST_MEMORY_ZIP_SWAP}": "Host Zip Swap Band",
    f"band_{METRIC_HOST_CPU_IMBALANCE_RATIO}": "Host CPU Imbalance Ratio Band",
    f"band_{METRIC_CPU_MONSTER_VM_SIZE_RATIO}": "CPU Monster VM Size Ratio Band",
    f"band_{METRIC_MEMORY_MONSTER_VM_SIZE_RATIO}": "Memory Monster VM Size Ratio Band",
}

# Confirmed directly against ops.vcf.gillaspy.org via
# /api/adapterkinds/VMWARE/resourcekinds/{HostSystem,ClusterComputeResource}/statkeys.
# There's no native "monster VM" statkey (confirmed absent from the live
# catalog, and NUMA topology isn't exposed via SuiteAPI) -- monster VM
# size ratios are computed in traversal.py as a per-VM proxy instead, in the
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
