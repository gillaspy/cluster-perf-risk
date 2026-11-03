# Cluster Performance Risk — Metrics Reference

Adapter kind: `ClusterPerfRisk`. **Since 2.0.0 the pack defines no objects of
its own.** Every value is written as a write-only attribute onto the existing
VMWARE `ClusterComputeResource` (cluster scope) and `HostSystem` (host scope)
objects, under the root `Performance Risk|<Group>|<Label>`. The tables below use
the internal metric keys; [Native attribute names](#native-attribute-names)
maps each key to its attribute. Each metric also has a `... Band` string
property (green/yellow/orange/red/unknown), plus a composite risk score,
band, band level and worst-band count per scope.

All formulas below are transcribed from `app/cluster.py`, `app/host.py`,
`app/traversal.py`, and `app/scoring.py`.

---

## Which data counts

These rules apply to every metric below.

- **Powered-on VMs only.** A VM counts only when its property
  `summary|runtime|powerState` is `Powered On`; a VM without that property
  does not count. Powered-off VMs are left out of the worst/P90 samples, the
  vCPU and memory totals, overcommit and the monster VM ratios. Their stats
  are not even read.
- **Stale stats are no data.** A stat whose latest sample is more than
  `STALE_AFTER_MINUTES` (10, two collection cycles) older than the newest
  sample VCF Operations returned in the same request is no data, never its
  last known value. Both timestamps come from VCF Operations, so the
  collector's clock plays no part. As a backstop for the case where nothing
  updates at all (the vCenter adapter stopped), a sample more than 15
  minutes older than the collector's clock (10 +
  `CLOCK_SKEW_TOLERANCE_MINUTES`, 5) is no data too. A stat without a
  timestamp is no data. Properties are never stale: VCF Operations stores a
  property only when it changes. Each cycle's INFO log line
  `Suite API: <n> calls, <f> failed, <s> stale, <t>s` counts them, by key.
- **Host memory is DRAM.** The host memory denominator (ballooned %, memory
  overcommit, memory monster VMs) is the DRAM tier stat
  `mem:DRAM|memory_tier_total_capacity` (KB), or `mem|host_provisioned` (KB)
  when that has no value. On a host with memory tiering,
  `mem|host_provisioned` includes the NVMe tier, which VMs do not run in.
  Neither has a value: the memory rows are no data.
- **No data is never a value.** A metric with no data is not published, its
  band is `unknown`, and it is left out of the composite.
- **Read in bulk.** Each cluster's hosts and VMs come from its relationships
  (one call for the hosts, one per host for its VMs); their stats and
  properties come from `POST /api/resources/stats/latest/query` and
  `POST /api/resources/properties/latest/query`, in chunks of 200 resource
  IDs (`BULK_MAX_RESOURCE_IDS`).

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
| `memory_ballooned_pct` | Memory Ballooned Pct | Per host: (`mem\|vmmemctl_average` KB ÷ host DRAM KB) × 100; result is the MAX across the cluster's hosts |
| `network_throughput_pct` | Network Throughput Pct | Per host: (`net\|usage_average` KBps × 8 ÷ 1000 → Mbps) ÷ `config\|network\|linkspeed` (Mbps, a resource property) × 100; result is the MAX across the cluster's hosts |
| `host_cpu_imbalance_ratio` | Host CPU Imbalance Ratio | MAX across the cluster's hosts of the host value (see host scope) |
| `cpu_monster_vm_size_ratio` | CPU Monster VM Size Ratio | MAX across the cluster's hosts of the host value (see host scope) |
| `memory_monster_vm_size_ratio` | Memory Monster VM Size Ratio | MAX across the cluster's hosts of the host value (see host scope) |
| `host_memory_zip_swap_pct` | Host Zip Swap Pct | MAX across the cluster's hosts of the host value (see host scope) |
| `vmotion_pct` | vMotion Pct | `summary\|number_vmotion` ÷ (`summary\|vm_count_per_host` × host count) × 100 |
| `worst_vcpu_ready_pct` | Worst vCPU Ready Pct | MAX of `cpu\|20_sec_peak_readyPct` across every powered-on VM in the cluster |
| `p90_vcpu_ready_pct` | P90 vCPU Ready Pct | 90th percentile (nearest-rank) of the same cluster-wide VM sample set |
| `worst_vcpu_costop_pct` | Worst vCPU Co-Stop Pct | MAX of `cpu\|20_sec_peak_costopPct` across every powered-on VM in the cluster |
| `p90_vcpu_costop_pct` | P90 vCPU Co-Stop Pct | P90 (nearest-rank) of the same cluster-wide VM sample set |
| `worst_memory_contention_pct` | Worst Memory Contention Pct | MAX of `mem\|20_sec_peak_host_contentionPct` across every powered-on VM in the cluster |
| `p90_memory_contention_pct` | P90 Memory Contention Pct | P90 (nearest-rank) of the same cluster-wide VM sample set |
| `worst_disk_latency_ms` | Worst Disk Latency Ms | MAX of `virtualDisk\|20_sec_peak_totalLatency_average` across every powered-on VM in the cluster |
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
| `host_memory_consumed_pct` | Memory Consumed Pct | This host's own native statkey `mem\|usage_average` (already a %). On a host with memory tiering it is consumed ÷ (DRAM + NVMe tier), not ÷ DRAM: VCF Operations has no DRAM-tier consumed stat with data, and consumed ÷ DRAM exceeds 100% by design on a tiered host (192% on a lab host) |
| `host_memory_ballooned_pct` | Memory Ballooned Pct | (`mem\|vmmemctl_average` KB ÷ host DRAM KB) × 100, this host only |
| `host_cpu_reservation_pct` | CPU Reservation Pct | (`cpu\|reservedCapacity_average` MHz ÷ `cpu\|totalCapacity_average` MHz, the capacity available to VMs) × 100. Before 2.2.0 the denominator was `cpu\|capacity_provisioned`, about 1.66× larger on the lab |
| `host_memory_reservation_pct` | Memory Reservation Pct | This host's own native statkey `mem\|reservedCapacityPct` (already a %) |
| `host_cpu_overcommit_ratio` | CPU Overcommit Ratio | vCPUs of this host's powered-on VMs (`cpu\|vcpus_allocated_on_all_powered_on_vms`, or the sum of their `config\|hardware\|num_Cpu` when that has no value) ÷ this host's core count (`hardware\|cpuInfo\|num_CpuCores`) |
| `host_memory_overcommit_ratio` | Memory Overcommit Ratio | Memory KB of this host's powered-on VMs (`mem\|memory_allocated_on_all_powered_on_vms`, or the sum of their `mem\|guest_provisioned`) ÷ this host's DRAM KB |
| `cpu_monster_vm_size_ratio` | CPU Monster VM Size Ratio | vCPUs of this host's largest powered-on VM ÷ the host's CPU monster size (`monster_vm_threshold_pct`% of its cores, default 50). 1 is exactly the monster size; 0 with no powered-on VMs |
| `memory_monster_vm_size_ratio` | Memory Monster VM Size Ratio | Memory of this host's largest powered-on VM ÷ the host's memory monster size (`monster_vm_memory_pct`% of its DRAM, default 40, at most `monster_vm_memory_cap_gb`, default 256 GB) |
| `host_cpu_imbalance_ratio` | Host CPU Imbalance Ratio | Running threads ÷ running cores: (`cpu\|utilization_average`% × threads) ÷ (`cpu\|coreUtilization_average`% × cores). Threads are 2 × cores when the properties `config\|hyperThread\|available` and `\|active` are both `true`. 1 is one running thread per running core; an idle host is 1 |
| `host_memory_zip_swap_pct` | Host Zip Swap Pct | (`mem\|compressed_average` KB + `mem\|swapout_average` KB) ÷ host DRAM KB × 100 |
| `worst_vcpu_ready_pct` | Worst vCPU Ready Pct | MAX of `cpu\|20_sec_peak_readyPct` across this host's own powered-on VMs |
| `p90_vcpu_ready_pct` | P90 vCPU Ready Pct | P90 (nearest-rank) of the same per-host VM sample set |
| `worst_vcpu_costop_pct` | Worst vCPU Co-Stop Pct | MAX of `cpu\|20_sec_peak_costopPct` across this host's own powered-on VMs |
| `p90_vcpu_costop_pct` | P90 vCPU Co-Stop Pct | P90 (nearest-rank) of the same per-host VM sample set |
| `worst_memory_contention_pct` | Worst Memory Contention Pct | MAX of `mem\|20_sec_peak_host_contentionPct` across this host's own powered-on VMs |
| `p90_memory_contention_pct` | P90 Memory Contention Pct | P90 (nearest-rank) of the same per-host VM sample set |
| `worst_disk_latency_ms` | Worst Disk Latency Ms | MAX of `virtualDisk\|20_sec_peak_totalLatency_average` across this host's own powered-on VMs |
| `p90_disk_latency_ms` | P90 Disk Latency Ms | P90 (nearest-rank) of the same per-host VM sample set |
| `host_memory_contention_pct` | Memory Contention Pct | This host's own native statkey `mem\|host_contentionPct` |
| `host_dropped_packets_pct` | Dropped Packets Pct | This host's own native statkey `net\|droppedPct` |
| `host_composite_risk_score` | Composite Risk Score | Weighted-worst-band composite of all metrics above — see [Composite Score Formula](#composite-score-formula) |

The composite band and one band property per metric above (except the
composite score itself) are also published.

Eight metric keys (`worst_vcpu_ready_pct`, `p90_vcpu_ready_pct`,
`worst_vcpu_costop_pct`, `p90_vcpu_costop_pct`, `worst_memory_contention_pct`,
`p90_memory_contention_pct`, `worst_disk_latency_ms`, `p90_disk_latency_ms`,
plus `host_memory_contention_pct`/`host_dropped_packets_pct`, and since 2.2.0
the zip swap, imbalance and monster VM size ratios) reuse the exact
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
6. **Composite band** (since 2.1.0) is the worst band among the known
   sub-metrics: `red > orange > yellow > green`. One red sub-metric makes the
   object red, however many are green. The band no longer comes from the
   score: one red sub-metric among greens scores 63-66, which the old score
   bands (`≥90 red, ≥80 orange, ≥60 yellow`) drew yellow. The score ranges of
   the bands overlap (green 0, yellow 42-60, orange 56-80, red 63-90), so
   color by the band, not by score thresholds.
7. **Risk Band Level** is the band as a number: `green 0, yellow 1, orange 2,
   red 3`. Dashboards color by it, because widgets color by a number, not a
   string. Use a widget with fixed bounds (the shipped dashboard's
   scoreboards, 1 yellow, 2 orange, 3 red): a heatmap stretches its colors
   over the values on screen, so its colors are relative.
8. **Metrics In Worst Band** is how many known sub-metrics are in that band:
   with a red band, 1 means a single red sub-metric, 4 means four.
9. If every sub-metric fails to collect, the composite is reported as
   `0.0` / `"unknown"` rather than a false "green", and neither Risk Band
   Level nor Metrics In Worst Band is published.

---

## Thresholds

Each band is `value ≤ green_max` green, `≤ yellow_max` yellow, `≤ orange_max`
orange, above that red. Pinned by `tests/test_threshold_tables.py`.

| Metric key | Scope | green_max | yellow_max | orange_max |
|---|---|---|---|---|
| `worst_vcpu_ready_pct` | both | 4 | 8 | 16 |
| `p90_vcpu_ready_pct` | both | 1 | 2 | 4 |
| `worst_vcpu_costop_pct` | both | 2 | 4 | 8 |
| `p90_vcpu_costop_pct` | both | 0.5 | 1 | 2 |
| `worst_memory_contention_pct` | both | 1 | 2 | 4 |
| `p90_memory_contention_pct` | both | 0.5 | 1 | 2 |
| `worst_disk_latency_ms` | both | 40 | 80 | 120 |
| `p90_disk_latency_ms` | both | 20 | 40 | 60 |
| `host_memory_contention_pct` | both | 0.25 | 0.5 | 1 |
| `host_dropped_packets_pct` | both | 0 | 0.2 | 0.4 |
| `host_memory_zip_swap_pct` | both | 0.25 | 0.5 | 1 |
| `host_cpu_imbalance_ratio` | both | 1.2 | 1.4 | 1.6 |
| `cpu_monster_vm_size_ratio` | both | 1 | 2 | 3 |
| `memory_monster_vm_size_ratio` | both | 1 | 2 | 3 |
| `cpu_thread_utilization_pct` | cluster | 60 | 80 | 90 |
| `memory_ballooned_pct` | cluster | 1 | 2 | 4 |
| `network_throughput_pct` | cluster | 1 | 2 | 4 |
| `disk_iops` | cluster | 25000 | 50000 | 100000 |
| `cluster_cpu_imbalance` | cluster | 0.05 | 0.08 | 0.12 |
| `vmotion_pct` | cluster | 1 | 2 | 4 |
| `cluster_cpu_overcommit_ratio` | cluster | 1 | 2 | 3 |
| `cluster_memory_overcommit_ratio` | cluster | 1 | 1.25 | 1.5 |
| `host_cpu_thread_utilization_pct` | host | 60 | 80 | 90 |
| `host_memory_consumed_pct` | host | 80 | 90 | 95 |
| `host_memory_ballooned_pct` | host | 1 | 2 | 4 |
| `host_cpu_reservation_pct` | host | 10 | 40 | 60 |
| `host_memory_reservation_pct` | host | 10 | 40 | 60 |
| `host_cpu_overcommit_ratio` | host | 1 | 2 | 3 |
| `host_memory_overcommit_ratio` | host | 1 | 1.4 | 1.8 |

New in 2.2.0: `host_memory_zip_swap_pct`, `host_cpu_imbalance_ratio`
(replaces `highest_host_cpu_imbalance_pct`, 5/10/20), `cpu_monster_vm_size_ratio`
and `memory_monster_vm_size_ratio` (replace `cluster_cpu_monster_vm_ratio`,
`cluster_memory_monster_vm_ratio`, 1/2/4, and `host_monster_vm_count`, 0/1/2).

Changed in 2.1.0: `p90_vcpu_costop_pct` (was 1/2/4), `memory_ballooned_pct`
(was 1/1.25/2), `host_memory_overcommit_ratio` (was 1/1.4/1.6),
`host_cpu_reservation_pct` and `host_memory_reservation_pct` (were 40/60/80).

---

## Notes

- Monster VM settings (adapter instance, Advanced): **Monster VM CPU (% of
  host cores)** (`monster_vm_threshold_pct`, default 50, 1-100), **Monster VM
  Memory (% of host DRAM)** (`monster_vm_memory_pct`, default 40, 1-100) and
  **Monster VM Memory Cap (GB)** (`monster_vm_memory_cap_gb`, default 256). A
  VM above its host's monster size is a proxy for "may not fit in one NUMA
  node"; NUMA topology itself is not exposed via SuiteAPI. An empty or
  invalid value uses the default and logs a warning.
- All VM-level "worst"/"p90" pairs use nearest-rank percentile (not
  interpolated), chosen for transparency at the small VM-count sample sizes
  typical of a single cluster or host.
- Several formulas are substitutes for statkeys that exist in the original
  risk-matrix design but are not monitored on real vSphere/VCF Operations
  instances (e.g. memory contention in place of memory latency) — see the inline
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
| Cluster | `cluster_cpu_imbalance` | `Performance Risk|Balance|DRS CPU Imbalance` |
| Cluster | `vmotion_pct` | `Performance Risk|Balance|vMotion Pct` |
| Cluster | `memory_ballooned_pct` | `Performance Risk|Memory|Max Host Ballooned Pct` |
| Cluster | `cluster_memory_overcommit_ratio` | `Performance Risk|Memory|Overcommit Ratio` |
| Cluster | `network_throughput_pct` | `Performance Risk|Network|Max Host Throughput Pct` |
| Cluster | `disk_iops` | `Performance Risk|Storage|Max Host Disk IOPS` |
| Cluster, Host | `host_memory_zip_swap_pct` | `Performance Risk|Memory|Host Zip Swap Pct` |
| Cluster, Host | `host_cpu_imbalance_ratio` | `Performance Risk|Balance|Host CPU Imbalance Ratio` |
| Cluster, Host | `cpu_monster_vm_size_ratio` | `Performance Risk|CPU|Monster VM Size Ratio` |
| Cluster, Host | `memory_monster_vm_size_ratio` | `Performance Risk|Memory|Monster VM Size Ratio` |
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
| Host | `host_memory_consumed_pct` | `Performance Risk|Memory|Consumed Pct` |
| Host | `host_memory_ballooned_pct` | `Performance Risk|Memory|Ballooned Pct` |
| Host | `host_memory_reservation_pct` | `Performance Risk|Memory|Reservation Pct` |
| Host | `host_memory_overcommit_ratio` | `Performance Risk|Memory|Overcommit Ratio` |
| Cluster, Host | composite score | `Performance Risk|Composite|Risk Score` |
| Cluster, Host | composite band | `Performance Risk|Composite|Risk Band` (property) |
| Cluster, Host | composite band as 0-3 | `Performance Risk|Composite|Risk Band Level` |
| Cluster, Host | known sub-metrics in the composite band | `Performance Risk|Composite|Metrics In Worst Band` |

Guarantees (enforced by `tests/test_native_projection.py`): every key starts
with `Performance Risk|`; none collides with a native statkey or the
`vCommunity|` namespace; the pack defines and emits no objects of its own and
sends no relationships, so native relationships are never rewritten. If a
native object cannot be matched, it is skipped and logged, never guessed.
