"""2.2.0: memory zip swap, CPU imbalance as threads per core, CPU reservation
against totalCapacity, monster VM size ratios."""
import pytest
import traversal

KB_PER_GB = 1024 * 1024


def snapshot(host_stats, vm_stats=None, host_props=None):
    """One cluster c1 with one host h1 and the given powered-on VMs."""
    vm_stats = vm_stats or {}
    stats = {("h1", k): v for k, v in host_stats.items()}
    for vm, s in vm_stats.items():
        stats.update({(vm, k): v for k, v in s.items()})
    props = {("h1", k): v for k, v in (host_props or {}).items()}
    return traversal.ClusterSnapshot("c1", [("h1", "esx01")], {"h1": [(v, v) for v in vm_stats]}, stats, props)


DRAM = {"mem:DRAM|memory_tier_total_capacity": 100.0}


@pytest.mark.parametrize("compressed, swapout, expected", [
    (0.5, 0.25, 0.75),
    (0.0, 0.0, 0.0),
    (None, 0.25, None),   # half a sum is no data
    (0.5, None, None),
])
def test_zip_swap_is_compressed_plus_swapped_over_dram(compressed, swapout, expected):
    host = dict(DRAM)
    if compressed is not None:
        host["mem|compressed_average"] = compressed
    if swapout is not None:
        host["mem|swapout_average"] = swapout
    cluster, ((_, _, h),) = traversal.collect_cluster_and_host_metrics(snapshot(host), 50)
    assert h["host_memory_zip_swap_pct"] == expected
    assert cluster["host_memory_zip_swap_pct"] == expected


def test_zip_swap_without_dram_is_no_data():
    snap = snapshot({"mem|compressed_average": 1.0, "mem|swapout_average": 1.0})
    _, ((_, _, h),) = traversal.collect_cluster_and_host_metrics(snap, 50)
    assert h["host_memory_zip_swap_pct"] is None


def imbalance(thread_util, core_util, ht=("true", "true"), cores=16):
    host = {"cpu|utilization_average": thread_util, "cpu|coreUtilization_average": core_util,
            "hardware|cpuInfo|num_CpuCores": cores}
    host = {k: v for k, v in host.items() if v is not None}
    props = {"config|hyperThread|available": ht[0], "config|hyperThread|active": ht[1]}
    cluster, ((_, _, h),) = traversal.collect_cluster_and_host_metrics(snapshot(host, host_props=props), 50)
    assert cluster["host_cpu_imbalance_ratio"] == h["host_cpu_imbalance_ratio"]
    return h["host_cpu_imbalance_ratio"]


def test_imbalance_is_running_threads_per_running_core():
    # Lab host05, 2026-10-30: 16.41 % of 32 threads, 28.47 % of 16 cores.
    assert imbalance(16.41, 28.47) == pytest.approx((0.1641 * 32) / (0.2847 * 16))
    assert imbalance(25, 50) == pytest.approx(1.0)    # one thread per core
    assert imbalance(50, 50) == pytest.approx(2.0)    # both threads of every running core


def test_imbalance_without_hyperthreading_uses_cores_as_threads():
    assert imbalance(50, 50, ht=("true", "false")) == pytest.approx(1.0)
    assert imbalance(50, 50, ht=("false", "false")) == pytest.approx(1.0)


def test_idle_host_is_not_imbalanced_and_missing_data_is_none():
    assert imbalance(0, 0) == 1.0
    assert imbalance(None, 10) is None
    assert imbalance(10, None) is None
    assert imbalance(10, 10, cores=None) is None


def test_cluster_imbalance_is_the_worst_host():
    stats = {}
    for h, (t, c) in {"h1": (25, 50), "h2": (40, 50)}.items():
        stats.update({(h, "cpu|utilization_average"): t, (h, "cpu|coreUtilization_average"): c,
                      (h, "hardware|cpuInfo|num_CpuCores"): 16})
    props = {(h, k): "true" for h in ("h1", "h2") for k in ("config|hyperThread|available", "config|hyperThread|active")}
    snap = traversal.ClusterSnapshot("c1", [("h1", "a"), ("h2", "b")], {}, stats, props)
    cluster, _ = traversal.collect_cluster_and_host_metrics(snap, 50)
    assert cluster["host_cpu_imbalance_ratio"] == pytest.approx(1.6)


def test_cpu_reservation_is_against_total_capacity():
    host = {"cpu|reservedCapacity_average": 6000.0, "cpu|totalCapacity_average": 24000.0,
            "cpu|capacity_provisioned": 40000.0}
    snap = traversal.ClusterSnapshot("c1", [("h1", "esx01")], {},
                                     {("h1", k): v for k, v in host.items() if k != "cpu|capacity_provisioned"}, {})
    _, ((_, _, h),) = traversal.collect_cluster_and_host_metrics(snap, 50)
    assert h["host_cpu_reservation_pct"] == 25.0
