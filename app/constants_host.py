"""
Constants specific to the host_perf_risk (ESXi Performance Risk) object type.
Metric keys reused as-is from the cluster scope (worst/p90 VM metrics, host
memory contention/dropped packets) live in constants_shared.py instead.

Own composite score/band, own BAND_BOUNDS/WEIGHTS entries (see
thresholds_host.py) -- independently tunable from the cluster composite even
where numbers currently coincide.

host_cpu_overcommit_ratio / host_memory_overcommit_ratio are DERIVED, not
native: cpu|vcpus_to_cores_allocation_ratio and
mem|virtual_to_physical_memory_allocation_ratio (used at cluster scope) were
confirmed ABSENT from the HostSystem statkey catalog entirely (2026-08-17) --
they only exist on ClusterComputeResource, despite the original handoff
describing them as "same statkey, this host's own value". Derived instead as
(sum of this host's VMs' vCPU or memory) / (this host's cores or memory),
mirroring the cluster stat's own documented definition ("vCPUs allocated to
powered on VMs / physical cores") using the exact per-VM data already
collected in traversal.py's shared VM pass.
"""
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

OBJECT_KIND_HOST_RISK = "host_perf_risk"
OBJECT_LABEL_HOST_RISK = "ESXi Performance Risk"

IDENTIFIER_HOST_VCF_ID = "host_vcf_id"
IDENTIFIER_HOST_NAME = "host_name"
# Non-unique context identifier linking a host object back to its cluster's
# display name -- mirrors IDENTIFIER_CLUSTER_NAME's is_part_of_uniqueness=False.
IDENTIFIER_HOST_CLUSTER_NAME = "cluster_name"

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

# Host-object-only statkeys, confirmed live 2026-08-17 (defaultMonitored:
# True, real data) against ops.vcf.gillaspy.org.
HOST_MEMORY_USAGE_STATKEY = "mem|usage_average"  # already a %, direct
HOST_CPU_RESERVED_STATKEY = "cpu|reservedCapacity_average"  # MHz
HOST_CPU_CAPACITY_STATKEY = "cpu|capacity_provisioned"  # MHz
HOST_MEMORY_RESERVED_PCT_STATKEY = "mem|reservedCapacityPct"  # already a %, direct

HOST_BAND_PROPERTY_LABELS = {
    f"band_{HOST_METRIC_CPU_THREAD_UTILIZATION}": "CPU Thread Utilization Band",
    f"band_{HOST_METRIC_MEMORY_CONSUMED}": "Memory Consumed Band",
    f"band_{HOST_METRIC_MEMORY_BALLOONED}": "Memory Ballooned Band",
    f"band_{HOST_METRIC_CPU_RESERVATION}": "CPU Reservation Band",
    f"band_{HOST_METRIC_MEMORY_RESERVATION}": "Memory Reservation Band",
    f"band_{HOST_METRIC_CPU_OVERCOMMIT_RATIO}": "CPU Overcommit Ratio Band",
    f"band_{HOST_METRIC_MEMORY_OVERCOMMIT_RATIO}": "Memory Overcommit Ratio Band",
    f"band_{HOST_METRIC_MONSTER_VM_COUNT}": "Monster VM Count Band",
    # Shared VM-level inputs, reusing the cluster-scope metric keys (see
    # constants_shared.py).
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
