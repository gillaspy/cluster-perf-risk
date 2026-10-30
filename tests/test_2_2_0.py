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
