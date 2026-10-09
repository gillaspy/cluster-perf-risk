# Cluster Performance Risk — Metrics Reference

Adapter kind: `ClusterPerfRisk`. **Since 2.0.0 the pack defines no objects of
its own.** Every value is written as a write-only attribute onto the existing
VMWARE `ClusterComputeResource` (cluster scope) and `HostSystem` (host scope)
objects, under the root `Performance Risk|<Group>|<Label>`. The tables below use
the internal metric keys; [Native attribute names](#native-attribute-names)
maps each key to its attribute. Each metric also has a `... Band` string
property (green/yellow/orange/red/unknown), plus a composite risk score and
band per scope.

All formulas below are transcribed from `app/cluster.py`, `app/host.py`,
`app/traversal.py`, and `app/scoring.py`.

---

## Cluster scope (ClusterComputeResource)

The native cluster object is matched by its Suite API `resourceKey`; its
existing relationships (cluster -> hosts) are native and untouched.

| Metric key | Label | Formula |
|---|---|---|
| `cpu_thread_utilization_pct` | Cpu Thread Utilization Pct | MAX across the cluster's hosts of native statkey `cpu\|utilization_average` |
| `disk_iops` | Disk Iops | MAX across the cluster's hosts of native statkey `disk\|commandsAveraged_average` |
| `cluster_cpu_imbalance` | Cluster Cpu Imbalance | Cluster-level native statkey `clusterServices\|total_imbalance`, divided by 1000 (native value is in thousandths of a standard deviation) |
| `cluster_cpu_overcommit_ratio` | Cluster Cpu Overcommit Ratio | Cluster-level native statkey `cpu\|vcpus_to_cores_allocation_ratio` (ClusterComputeResource-only) |
| `cluster_memory_overcommit_ratio` | Cluster Memory Overcommit Ratio | Cluster-level native statkey `mem\|virtual_to_physical_memory_allocation_ratio` (ClusterComputeResource-only) |
| `memory_ballooned_pct` | Memory Ballooned Pct | Per host: (`mem\|vmmemctl_average` KB ÷ `mem\|host_provisioned` KB) × 100; result is the MAX across the cluster's hosts |
| `network_throughput_pct` | Network Throughput Pct | Per host: (`net\|usage_average` KBps × 8 ÷ 1000 → Mbps) ÷ `config\|network\|linkspeed` (Mbps, a resource property) × 100; result is the MAX across the cluster's hosts |
| `highest_host_cpu_imbalance_pct` | Highest ESXi CPU Imbalance Pct | Population standard deviation (`statistics.pstdev`) of `cpu\|utilization_average` across the cluster's hosts (requires ≥2 hosts with data) — a synthetic proxy; no native per-host imbalance statkey exists |
| `cluster_cpu_monster_vm_ratio` | Cluster CPU Monster VM Ratio | (count of VMs in the cluster whose vCPU count exceeds `monster_vm_threshold_pct`% of their host's total cores) ÷ host count |
| `cluster_memory_monster_vm_ratio` | Cluster Memory Monster VM Ratio | (count of VMs in the cluster whose memory exceeds `monster_vm_threshold_pct`% of their host's total memory) ÷ host count |
| `vmotion_pct` | vMotion Pct | `summary\|number_vmotion` ÷ (`summary\|vm_count_per_host` × host count) × 100 |
| `worst_vcpu_ready_pct` | Worst vCPU Ready Pct | MAX of `cpu\|20_sec_peak_readyPct` across every VM in the cluster |
| `p90_vcpu_ready_pct` | P90 vCPU Ready Pct | 90th percentile (nearest-rank) of the same cluster-wide VM sample set |
| `worst_vcpu_costop_pct` | Worst vCPU Co-Stop Pct | MAX of `cpu\|20_sec_peak_costopPct` across every VM in the cluster |
| `p90_vcpu_costop_pct` | P90 vCPU Co-Stop Pct | P90 (nearest-rank) of the same cluster-wide VM sample set |
| `worst_memory_contention_pct` | Worst Memory Contention Pct | MAX of `mem\|20_sec_peak_host_contentionPct` across every VM in the cluster |
| `p90_memory_contention_pct` | P90 Memory Contention Pct | P90 (nearest-rank) of the same cluster-wide VM sample set |
| `worst_disk_latency_ms` | Worst Disk Latency Ms | MAX of `virtualDisk\|20_sec_peak_totalLatency_average` across every VM in the cluster |
| `p90_disk_latency_ms` | P90 Disk Latency Ms | P90 (nearest-rank) of the same cluster-wide VM sample set |
| `host_memory_contention_pct` | Host Memory Contention Pct | MAX across the cluster's hosts of native statkey `mem\|host_contentionPct` |
| `host_dropped_packets_pct` | Host Dropped Packets Pct | MAX across the cluster's hosts of native statkey `net\|droppedPct` |
| `composite_risk_score` | Composite Risk Score | Weighted-worst-band composite of all metrics above — see [Composite Score Formula](#composite-score-formula) |

The composite band and one band property per metric above are also published.

---

## Host scope (HostSystem)

The native host object is matched by its Suite API `resourceKey`.

| Metric key | Label | Formula |
|---|---|---|
| `host_cpu_thread_utilization_pct` | CPU Thread Utilization Pct | This host's own native statkey `cpu\|utilization_average` |
| `host_memory_consumed_pct` | Memory Consumed Pct | This host's own native statkey `mem\|usage_average` (already a %) |
| `host_memory_ballooned_pct` | Memory Ballooned Pct | (`mem\|vmmemctl_average` KB ÷ `mem\|host_provisioned` KB) × 100, this host only |
| `host_cpu_reservation_pct` | CPU Reservation Pct | (`cpu\|reservedCapacity_average` MHz ÷ `cpu\|capacity_provisioned` MHz) × 100 |
| `host_memory_reservation_pct` | Memory Reservation Pct | This host's own native statkey `mem\|reservedCapacityPct` (already a %) |
| `host_cpu_overcommit_ratio` | CPU Overcommit Ratio | (sum of this host's VMs' vCPU count, `config\|hardware\|num_Cpu`) ÷ this host's core count (`hardware\|cpuInfo\|num_CpuCores`) — derived; no native HostSystem statkey exists |
| `host_memory_overcommit_ratio` | Memory Overcommit Ratio | (sum of this host's VMs' memory KB, `mem\|guest_provisioned`) ÷ this host's total memory KB (`mem\|host_provisioned`) — derived; no native HostSystem statkey exists |
| `host_monster_vm_count` | Monster VM Count | Count of VMs on this host whose vCPU count exceeds `monster_vm_threshold_pct`% of the host's cores, OR whose memory exceeds `monster_vm_threshold_pct`% of the host's memory |
| `worst_vcpu_ready_pct` | Worst vCPU Ready Pct | MAX of `cpu\|20_sec_peak_readyPct` across this host's own VMs |
| `p90_vcpu_ready_pct` | P90 vCPU Ready Pct | P90 (nearest-rank) of the same per-host VM sample set |
| `worst_vcpu_costop_pct` | Worst vCPU Co-Stop Pct | MAX of `cpu\|20_sec_peak_costopPct` across this host's own VMs |
| `p90_vcpu_costop_pct` | P90 vCPU Co-Stop Pct | P90 (nearest-rank) of the same per-host VM sample set |
| `worst_memory_contention_pct` | Worst Memory Contention Pct | MAX of `mem\|20_sec_peak_host_contentionPct` across this host's own VMs |
| `p90_memory_contention_pct` | P90 Memory Contention Pct | P90 (nearest-rank) of the same per-host VM sample set |
| `worst_disk_latency_ms` | Worst Disk Latency Ms | MAX of `virtualDisk\|20_sec_peak_totalLatency_average` across this host's own VMs |
| `p90_disk_latency_ms` | P90 Disk Latency Ms | P90 (nearest-rank) of the same per-host VM sample set |
| `host_memory_contention_pct` | Memory Contention Pct | This host's own native statkey `mem\|host_contentionPct` |
| `host_dropped_packets_pct` | Dropped Packets Pct | This host's own native statkey `net\|droppedPct` |
| `host_composite_risk_score` | Composite Risk Score | Weighted-worst-band composite of all metrics above — see [Composite Score Formula](#composite-score-formula) |

The composite band and one band property per metric above (except the
composite score itself) are also published.

Eight metric keys (`worst_vcpu_ready_pct`, `p90_vcpu_ready_pct`,
`worst_vcpu_costop_pct`, `p90_vcpu_costop_pct`, `worst_memory_contention_pct`,
`p90_memory_contention_pct`, `worst_disk_latency_ms`, `p90_disk_latency_ms`,
plus `host_memory_contention_pct`/`host_dropped_packets_pct`) reuse the exact
same metric key as the cluster scope — same key, computed at a different
scope (this host's VMs only vs. the whole cluster's VMs).

---

## Composite Score Formula

Both `composite_risk_score` (cluster) and `host_composite_risk_score` (host)
use the same weighted-worst-band algorithm (`app/scoring.py`,
`compute_composite`), against that scope's own merged band-bounds and
weight tables (shared thresholds from `thresholds_shared.py` merged with
`thresholds_cluster.py` or `thresholds_host.py`):

1. Every known sub-metric is classified into a band — `green`, `yellow`,
   `orange`, or `red` — by comparing its value against that metric's
   `green_max` / `yellow_max` / `orange_max` bounds. A metric with no value,
   or no bounds entry, is `unknown` and excluded from the composite math
   entirely (an unknown metric does not get silently treated as green).
2. Each band maps to a floor score: `green=0, yellow=60, orange=80, red=90`.
3. **Worst-band term:** the single worst band among all known sub-metrics,
   by its floor score.
4. **Weighted-average term:** `Σ(band_floor × metric_weight) / Σ(metric_weight)`
   across all known sub-metrics (per-metric weights come from each object
   type's `WEIGHTS` table; default weight is `1.0` if unspecified).
5. **Composite score** = `round(min(100, max(0, 0.7 × worst_floor + 0.3 × weighted_average)), 1)`
   — 70% weight on the single worst sub-metric's band floor, 30% on the
   weighted average across all sub-metrics, so one red sub-metric can't be
   diluted into invisibility by several green ones.
6. **Composite band** is then derived from the composite score itself:
   `≥90 → red`, `≥80 → orange`, `≥60 → yellow`, else `green`.
7. If every sub-metric fails to collect, the composite is reported as
   `0.0` / `"unknown"` rather than a false "green".

---

## Notes

- `monster_vm_threshold_pct` (default `50`) is a user-configurable adapter
  parameter — a VM counts as a "monster VM" when its vCPU count or memory
  exceeds that percentage of its host's total cores/memory (a proxy for
  "may not fit in one NUMA node"; NUMA topology itself is not exposed via
  SuiteAPI).
- All VM-level "worst"/"p90" pairs use nearest-rank percentile (not
  interpolated), chosen for transparency at the small VM-count sample sizes
  typical of a single cluster or host.
- Several formulas are substitutes for statkeys that exist in the original
  risk-matrix design but are not monitored on real vSphere/VCF Operations
  instances (e.g. memory contention in place of memory latency, host memory
  contention in place of a swap%+compressed% derivation) — see the inline
  comments in `constants_shared.py` and `constants_cluster.py` for the full
  investigation history behind each substitution.

---

## Native attribute names

Attributes are written to the native object of the matching scope under
`Performance Risk|<Group>|<Label>` (metrics) and
`Performance Risk|<Group>|<Label> Band` (string properties). Mapping lives in
`app/constants_native.py`.

| Scope | Internal key | Attribute (metric) |
|---|---|---|
| Cluster | `worst_vcpu_ready_pct` | `Performance Risk|Contention|Worst vCPU Ready Pct` |
| Cluster | `p90_vcpu_ready_pct` | `Performance Risk|Contention|P90 vCPU Ready Pct` |
| Cluster | `worst_vcpu_costop_pct` | `Performance Risk|Contention|Worst vCPU Co-Stop Pct` |
| Cluster | `p90_vcpu_costop_pct` | `Performance Risk|Contention|P90 vCPU Co-Stop Pct` |
| Cluster | `worst_memory_contention_pct` | `Performance Risk|Contention|Worst VM Memory Contention Pct` |
| Cluster | `p90_memory_contention_pct` | `Performance Risk|Contention|P90 VM Memory Contention Pct` |
| Cluster | `host_memory_contention_pct` | `Performance Risk|Contention|Host Memory Contention Pct` |
| Cluster | `worst_disk_latency_ms` | `Performance Risk|Storage|Worst Disk Latency Ms` |
| Cluster | `p90_disk_latency_ms` | `Performance Risk|Storage|P90 Disk Latency Ms` |
| Cluster | `host_dropped_packets_pct` | `Performance Risk|Network|Host Dropped Packets Pct` |
| Cluster | `cpu_thread_utilization_pct` | `Performance Risk|CPU|Max Host Thread Utilization Pct` |
| Cluster | `cluster_cpu_overcommit_ratio` | `Performance Risk|CPU|Overcommit Ratio` |
| Cluster | `cluster_cpu_monster_vm_ratio` | `Performance Risk|CPU|Monster VM Ratio` |
| Cluster | `highest_host_cpu_imbalance_pct` | `Performance Risk|Balance|Host CPU Imbalance Pct` |
| Cluster | `cluster_cpu_imbalance` | `Performance Risk|Balance|DRS CPU Imbalance` |
| Cluster | `vmotion_pct` | `Performance Risk|Balance|vMotion Pct` |
| Cluster | `memory_ballooned_pct` | `Performance Risk|Memory|Max Host Ballooned Pct` |
| Cluster | `cluster_memory_overcommit_ratio` | `Performance Risk|Memory|Overcommit Ratio` |
| Cluster | `cluster_memory_monster_vm_ratio` | `Performance Risk|Memory|Monster VM Ratio` |
| Cluster | `network_throughput_pct` | `Performance Risk|Network|Max Host Throughput Pct` |
| Cluster | `disk_iops` | `Performance Risk|Storage|Max Host Disk IOPS` |
| Host | `worst_vcpu_ready_pct` | `Performance Risk|Contention|Worst vCPU Ready Pct` |
| Host | `p90_vcpu_ready_pct` | `Performance Risk|Contention|P90 vCPU Ready Pct` |
| Host | `worst_vcpu_costop_pct` | `Performance Risk|Contention|Worst vCPU Co-Stop Pct` |
| Host | `p90_vcpu_costop_pct` | `Performance Risk|Contention|P90 vCPU Co-Stop Pct` |
| Host | `worst_memory_contention_pct` | `Performance Risk|Contention|Worst VM Memory Contention Pct` |
| Host | `p90_memory_contention_pct` | `Performance Risk|Contention|P90 VM Memory Contention Pct` |
| Host | `host_memory_contention_pct` | `Performance Risk|Contention|Host Memory Contention Pct` |
| Host | `worst_disk_latency_ms` | `Performance Risk|Storage|Worst Disk Latency Ms` |
| Host | `p90_disk_latency_ms` | `Performance Risk|Storage|P90 Disk Latency Ms` |
| Host | `host_dropped_packets_pct` | `Performance Risk|Network|Host Dropped Packets Pct` |
| Host | `host_cpu_thread_utilization_pct` | `Performance Risk|CPU|Thread Utilization Pct` |
| Host | `host_cpu_reservation_pct` | `Performance Risk|CPU|Reservation Pct` |
| Host | `host_cpu_overcommit_ratio` | `Performance Risk|CPU|Overcommit Ratio` |
| Host | `host_monster_vm_count` | `Performance Risk|CPU|Monster VM Count` |
| Host | `host_memory_consumed_pct` | `Performance Risk|Memory|Consumed Pct` |
| Host | `host_memory_ballooned_pct` | `Performance Risk|Memory|Ballooned Pct` |
| Host | `host_memory_reservation_pct` | `Performance Risk|Memory|Reservation Pct` |
| Host | `host_memory_overcommit_ratio` | `Performance Risk|Memory|Overcommit Ratio` |
| Cluster, Host | composite score | `Performance Risk|Composite|Risk Score` |
| Cluster, Host | composite band | `Performance Risk|Composite|Risk Band` (property) |

Guarantees (enforced by `tests/test_native_projection.py`): every key starts
with `Performance Risk|`; none collides with a native statkey or the
`vCommunity|` namespace; the pack defines and emits no objects of its own and
sends no relationships, so native relationships are never rewritten. If a
native object cannot be matched, it is skipped and logged, never guessed.
