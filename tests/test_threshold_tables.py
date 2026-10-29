"""Pins every band threshold table (green_max, yellow_max, orange_max). A
change here changes object colors after upgrading: update MIGRATION.md and
docs/METRICS.md with it."""
import thresholds_cluster
import thresholds_host
import thresholds_shared

SHARED = {
    "worst_vcpu_ready_pct": (4, 8, 16),
    "p90_vcpu_ready_pct": (1, 2, 4),
    "worst_vcpu_costop_pct": (2, 4, 8),
    "p90_vcpu_costop_pct": (0.5, 1, 2),             # 2.1.0, was 1/2/4
    "worst_memory_contention_pct": (1, 2, 4),
    "p90_memory_contention_pct": (0.5, 1, 2),
    "worst_disk_latency_ms": (40, 80, 120),
    "p90_disk_latency_ms": (20, 40, 60),
    "host_memory_contention_pct": (0.25, 0.5, 1),
    "host_dropped_packets_pct": (0, 0.2, 0.4),
}
CLUSTER = {
    "cpu_thread_utilization_pct": (60, 80, 90),
    "memory_ballooned_pct": (1, 2, 4),              # 2.1.0, was 1/1.25/2
    "network_throughput_pct": (1, 2, 4),
    "disk_iops": (25000, 50000, 100000),
    "highest_host_cpu_imbalance_pct": (5, 10, 20),
    "cluster_cpu_imbalance": (0.05, 0.08, 0.12),
    "vmotion_pct": (1, 2, 4),
    "cluster_cpu_overcommit_ratio": (1, 2, 3),
    "cluster_memory_overcommit_ratio": (1, 1.25, 1.5),
    "cluster_cpu_monster_vm_ratio": (1, 2, 4),
    "cluster_memory_monster_vm_ratio": (1, 2, 4),
}
HOST = {
    "host_cpu_thread_utilization_pct": (60, 80, 90),
    "host_memory_consumed_pct": (80, 90, 95),
    "host_memory_ballooned_pct": (1, 2, 4),
    "host_cpu_reservation_pct": (10, 40, 60),       # 2.1.0, was 40/60/80
    "host_memory_reservation_pct": (10, 40, 60),    # 2.1.0, was 40/60/80
    "host_cpu_overcommit_ratio": (1, 2, 3),
    "host_memory_overcommit_ratio": (1, 1.4, 1.8),  # 2.1.0, was 1/1.4/1.6
    "host_monster_vm_count": (0, 1, 2),
}


def table(module):
    return {k: (v["green_max"], v["yellow_max"], v["orange_max"]) for k, v in module.BAND_BOUNDS.items()}


def test_shared_thresholds():
    assert table(thresholds_shared) == SHARED


def test_cluster_thresholds():
    assert table(thresholds_cluster) == CLUSTER


def test_host_thresholds():
    assert table(thresholds_host) == HOST


def test_bounds_are_ordered():
    for module in (thresholds_shared, thresholds_cluster, thresholds_host):
        for key, (g, y, o) in table(module).items():
            assert g <= y <= o, key
