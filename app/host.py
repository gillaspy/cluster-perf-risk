"""
Everything specific to the host_perf_risk (ESXi Performance Risk) object
type: its adapter definition and building its CollectResult object. The
6 "shared VM-level inputs" (worst/p90 vCPU ready, worst/p90 vCPU co-stop,
worst/p90 memory contention, worst/p90 disk latency, host memory contention,
host dropped packets) reuse the cluster-scope metric keys directly (see
constants_shared.py) -- confirmed 2026-08-17 that the bounds table is
identical for both cluster and host scope. All host_metric_values come from
traversal.collect_cluster_and_host_metrics(), computed from just this host's
own VMs.
"""
from typing import Optional

from aria.ops.definition.adapter_definition import AdapterDefinition
from aria.ops.object import Identifier
from aria.ops.object import Object
from aria.ops.result import CollectResult
from constants_host import HOST_BAND_PROPERTY_LABELS
from constants_host import HOST_METRIC_COMPOSITE_SCORE
from constants_host import HOST_METRIC_CPU_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_CPU_RESERVATION
from constants_host import HOST_METRIC_CPU_THREAD_UTILIZATION
from constants_host import HOST_METRIC_MEMORY_BALLOONED
from constants_host import HOST_METRIC_MEMORY_CONSUMED
from constants_host import HOST_METRIC_MEMORY_OVERCOMMIT_RATIO
from constants_host import HOST_METRIC_MEMORY_RESERVATION
from constants_host import HOST_METRIC_MONSTER_VM_COUNT
from constants_host import HOST_PROP_COMPOSITE_BAND
from constants_host import IDENTIFIER_HOST_CLUSTER_NAME
from constants_host import IDENTIFIER_HOST_NAME
from constants_host import IDENTIFIER_HOST_VCF_ID
from constants_host import OBJECT_KIND_HOST_RISK
from constants_host import OBJECT_LABEL_HOST_RISK
from constants_shared import ADAPTER_KIND
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
import scoring
import thresholds_host
import thresholds_shared

# Merged so compute_composite() sees both this object type's own bounds/weights
# and the ones it shares with the cluster object.
BAND_BOUNDS = {**thresholds_shared.BAND_BOUNDS, **thresholds_host.BAND_BOUNDS}
WEIGHTS = {**thresholds_shared.WEIGHTS, **thresholds_host.WEIGHTS}


def define_object_type(definition: AdapterDefinition) -> None:
    host_risk = definition.define_object_type(OBJECT_KIND_HOST_RISK, OBJECT_LABEL_HOST_RISK)
    host_risk.define_string_identifier(IDENTIFIER_HOST_VCF_ID, "Host VCF Resource ID")
    host_risk.define_string_identifier(
        IDENTIFIER_HOST_NAME, "Host Name", is_part_of_uniqueness=False
    )
    host_risk.define_string_identifier(
        IDENTIFIER_HOST_CLUSTER_NAME, "Cluster Name", is_part_of_uniqueness=False
    )

    # Host-only metrics.
    for metric_key, label in [
        (HOST_METRIC_CPU_THREAD_UTILIZATION, "CPU Thread Utilization Pct"),
        (HOST_METRIC_MEMORY_CONSUMED, "Memory Consumed Pct"),
        (HOST_METRIC_MEMORY_BALLOONED, "Memory Ballooned Pct"),
        (HOST_METRIC_CPU_RESERVATION, "CPU Reservation Pct"),
        (HOST_METRIC_MEMORY_RESERVATION, "Memory Reservation Pct"),
        (HOST_METRIC_CPU_OVERCOMMIT_RATIO, "CPU Overcommit Ratio"),
        (HOST_METRIC_MEMORY_OVERCOMMIT_RATIO, "Memory Overcommit Ratio"),
        (HOST_METRIC_MONSTER_VM_COUNT, "Monster VM Count"),
    ]:
        host_risk.define_metric(metric_key, label, is_kpi=True)
    # Shared VM-level inputs -- same metric keys as the cluster object,
    # computed here from just this host's own VMs. See constants_shared.py.
    for metric_key, label in [
        (METRIC_WORST_VCPU_READY, "Worst vCPU Ready Pct"),
        (METRIC_P90_VCPU_READY, "P90 vCPU Ready Pct"),
        (METRIC_WORST_VCPU_COSTOP, "Worst vCPU Co-Stop Pct"),
        (METRIC_P90_VCPU_COSTOP, "P90 vCPU Co-Stop Pct"),
        (METRIC_WORST_MEMORY_CONTENTION, "Worst Memory Contention Pct"),
        (METRIC_P90_MEMORY_CONTENTION, "P90 Memory Contention Pct"),
        (METRIC_WORST_DISK_LATENCY, "Worst Disk Latency Ms"),
        (METRIC_P90_DISK_LATENCY, "P90 Disk Latency Ms"),
        (METRIC_HOST_MEMORY_CONTENTION, "Memory Contention Pct"),
        (METRIC_HOST_DROPPED_PACKETS, "Dropped Packets Pct"),
    ]:
        host_risk.define_metric(metric_key, label, is_kpi=True)

    host_risk.define_metric(
        HOST_METRIC_COMPOSITE_SCORE,
        "Composite Risk Score",
        is_kpi=True,
        is_key_attribute=True,
    )
    host_risk.define_string_property(
        HOST_PROP_COMPOSITE_BAND, "Composite Risk Band", is_key_attribute=True
    )
    for band_key, band_label in HOST_BAND_PROPERTY_LABELS.items():
        host_risk.define_string_property(band_key, band_label)


def build_object(
    result: CollectResult,
    host_id: str,
    host_name: str,
    cluster_name: str,
    host_metric_values: dict[str, Optional[float]],
) -> Object:
    composite_score, composite_band, per_metric_band = scoring.compute_composite(
        host_metric_values, BAND_BOUNDS, WEIGHTS
    )

    host_obj = result.object(
        ADAPTER_KIND,
        OBJECT_KIND_HOST_RISK,
        f"{host_name} - Perf Risk",
        identifiers=[
            Identifier(IDENTIFIER_HOST_VCF_ID, host_id),
            Identifier(
                IDENTIFIER_HOST_NAME,
                host_name,
                is_part_of_uniqueness=False,
            ),
            Identifier(
                IDENTIFIER_HOST_CLUSTER_NAME,
                cluster_name,
                is_part_of_uniqueness=False,
            ),
        ],
    )

    for metric_key, value in host_metric_values.items():
        if value is not None:
            host_obj.with_metric(metric_key, value)
        band = per_metric_band.get(metric_key, "unknown")
        host_obj.with_property(f"band_{metric_key}", band)

    host_obj.with_metric(HOST_METRIC_COMPOSITE_SCORE, composite_score)
    host_obj.with_property(HOST_PROP_COMPOSITE_BAND, composite_band)

    return host_obj
