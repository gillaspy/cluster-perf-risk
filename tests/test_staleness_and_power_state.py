"""2.1.0: a stale stat is no data, only powered-on VMs count, host memory is
DRAM, and stats/properties are read in bulk."""
from unittest import mock

import pytest
import suite_api
import traversal
from constants_shared import STALE_AFTER_MINUTES
from constants_shared import VM_POWER_STATE_PROPERTY
from test_visible_failures import FakeResponse
from test_visible_failures import client_returning

MIN = 60_000
NOW = 1_800_000_000_000


@pytest.fixture(autouse=True)
def fake_clock():
    suite_api.CALL_STATS.reset()
    with mock.patch.object(suite_api, "now_ms", return_value=NOW):
        yield


def stat(key, value, ts):
    return {"statKey": {"key": key}, "timestamps": [ts], "data": [value]}


def stats_response(*entries):
    """entries: (resource_id, [stat, ...])"""
    return FakeResponse(200, {"values": [
        {"resourceId": rid, "stat-list": {"stat": stats}} for rid, stats in entries]})


def test_fresh_sample_is_its_value():
    c = client_returning(stats_response(("r", [stat("k", 7.0, NOW - 4 * MIN)])))
    assert suite_api.bulk_latest_stats(c, ["r"], ["k"]) == {("r", "k"): 7.0}
    assert suite_api.CALL_STATS.stale == 0


def test_stale_sample_is_no_data_and_counted():
    c = client_returning(stats_response(("r", [stat("k", 7.0, NOW - (STALE_AFTER_MINUTES + 6) * MIN)])))
    assert suite_api.bulk_latest_stats(c, ["r"], ["k"]) == {}
    assert suite_api.CALL_STATS.stale == 1
    assert suite_api.CALL_STATS.stale_keys == {"k": 1}


def test_stale_relative_to_newest_sample_even_if_clock_is_behind():
    # The collector's clock is 20 minutes behind VCF Operations; "old" is 11
    # minutes older than the newest sample in the same response.
    with mock.patch.object(suite_api, "now_ms", return_value=NOW - 20 * MIN):
        c = client_returning(stats_response(
            ("old", [stat("k", 2.0, NOW - 11 * MIN)]),
            ("fresh", [stat("k", 1.0, NOW)]),
        ))
        assert suite_api.bulk_latest_stats(c, ["old", "fresh"], ["k"]) == {("fresh", "k"): 1.0}


def test_collector_clock_a_few_minutes_ahead_is_tolerated():
    c = client_returning(stats_response(("r", [stat("k", 3.0, NOW - (STALE_AFTER_MINUTES + 4) * MIN)])))
    assert suite_api.bulk_latest_stats(c, ["r"], ["k"]) == {("r", "k"): 3.0}


def test_sample_without_timestamp_is_no_data():
    c = client_returning(stats_response(("r", [{"statKey": {"key": "k"}, "data": [5.0]}])))
    assert suite_api.bulk_latest_stats(c, ["r"], ["k"]) == {}


def test_only_requested_keys_and_aggregate_fallback():
    c = client_returning(stats_response(("h", [
        stat("cpu:26|utilization_average", 99.0, NOW),     # an instance: ignored
        stat("cpu|utilization_average", 10.0, NOW),
        stat("disk:Aggregate of all instances|commandsAveraged_average", 500.0, NOW),
        stat("disk:vmhba0|commandsAveraged_average", 1.0, NOW),  # an instance: ignored
    ])))
    got = suite_api.bulk_latest_stats(
        c, ["h"], ["cpu|utilization_average", "disk|commandsAveraged_average", "mem|x"])
    assert got == {("h", "cpu|utilization_average"): 10.0,
                   ("h", "disk|commandsAveraged_average"): 500.0}


def test_bulk_requests_are_chunked():
    size = suite_api.BULK_MAX_RESOURCE_IDS
    ids = [f"vm{i}" for i in range(size * 2 + 1)]
    c = client_returning(*[stats_response() for _ in range(3)])
    suite_api.bulk_latest_stats(c, ids, ["k"])
    sent = [call.kwargs["json"]["resourceId"] for call in c.post.call_args_list]
    assert [len(s) for s in sent] == [size, size, 1]
    assert sum(sent, []) == ids
    assert suite_api.CALL_STATS.calls == 3


def test_a_failed_chunk_loses_only_its_resources():
    c = client_returning(FakeResponse(500), stats_response())
    ids = [f"vm{i}" for i in range(suite_api.BULK_MAX_RESOURCE_IDS + 1)]
    assert suite_api.bulk_latest_stats(c, ids, ["k"]) == {}
    assert (suite_api.CALL_STATS.calls, suite_api.CALL_STATS.failures) == (2, 1)


def test_properties_text_and_number():
    c = client_returning(FakeResponse(200, {"values": [
        {"resourceId": "vm1", "property-contents": {"property-content": [
            {"statKey": "summary|runtime|powerState", "timestamps": [NOW], "values": ["Powered On"]},
            {"statKey": "other|prop", "values": ["x"]}]}},
        {"resourceId": "h1", "property-contents": {"property-content": [
            {"statKey": "config|network|linkspeed", "timestamps": [NOW], "data": [10000.0]}]}},
    ]}))
    got = suite_api.bulk_latest_properties(
        c, ["vm1", "h1"], ["summary|runtime|powerState", "config|network|linkspeed"])
    assert got == {("vm1", "summary|runtime|powerState"): "Powered On",
                   ("h1", "config|network|linkspeed"): "10000.0"}


VM_STATS = {
    "vm-on": {"config|hardware|num_Cpu": 4, "mem|guest_provisioned": 4 * 1024 * 1024,
              "cpu|20_sec_peak_readyPct": 1.0},
    # Huge and badly contended -- must not show up anywhere.
    "vm-off": {"config|hardware|num_Cpu": 64, "mem|guest_provisioned": 512 * 1024 * 1024,
               "cpu|20_sec_peak_readyPct": 50.0},
    "vm-unknown": {"config|hardware|num_Cpu": 64, "cpu|20_sec_peak_readyPct": 40.0},
}
HOST_STATS = {"hardware|cpuInfo|num_CpuCores": 16, "mem|host_provisioned": 64 * 1024 * 1024}


def snapshot_with(power_states, host_stats=HOST_STATS):
    def stats(client, ids, keys):
        table = {**{"h1": host_stats}, **VM_STATS}
        return {(r, k): table[r][k] for r in ids for k in keys if k in table.get(r, {})}

    def props(client, ids, keys):
        return {(r, VM_POWER_STATE_PROPERTY): power_states[r] for r in ids
                if r in power_states and power_states[r] is not None}

    with mock.patch.object(traversal, "fetch_child_hosts", return_value=[("h1", "esx01")]), \
         mock.patch.object(traversal, "fetch_children_of_kind", return_value=[(v, v) for v in VM_STATS]), \
         mock.patch.object(traversal, "bulk_latest_stats", side_effect=stats) as s, \
         mock.patch.object(traversal, "bulk_latest_properties", side_effect=props):
        return traversal.fetch_cluster_snapshot(None, "c1"), s


def test_powered_off_vm_is_excluded_everywhere():
    snap, stats_calls = snapshot_with({"vm-on": "Powered On", "vm-off": "Powered Off", "vm-unknown": None})
    # Stats are not even read for VMs that are not powered on.
    vm_call = [c for c in stats_calls.call_args_list if c.args[2] == traversal.VM_STATKEYS]
    assert vm_call and vm_call[0].args[1] == ["vm-on"]
    assert snap.vms_not_powered_on == 2

    cluster, hosts = traversal.collect_cluster_and_host_metrics(snap)
    (_, _, h), = hosts
    assert cluster["worst_vcpu_ready_pct"] == 1.0 and cluster["p90_vcpu_ready_pct"] == 1.0
    assert h["host_cpu_overcommit_ratio"] == 4 / 16
    assert h["host_memory_overcommit_ratio"] == 4 / 64
    # Only vm-on (4 vCPU, 4 GB) counts: monster size is 8 vCPU (50% of 16
    # cores) and 25.6 GB (40% of 64 GB).
    assert h["cpu_monster_vm_size_ratio"] == cluster["cpu_monster_vm_size_ratio"] == 4 / 8
    assert h["memory_monster_vm_size_ratio"] == cluster["memory_monster_vm_size_ratio"] == 4 / 25.6


def test_snapshot_refuses_a_key_it_did_not_fetch():
    snap, _ = snapshot_with({"vm-on": "Powered On"})
    with pytest.raises(KeyError):
        snap.stat("h1", "not|fetched")


@pytest.mark.parametrize("dram, provisioned, expected", [
    (48.0, 64.0, 48.0),    # tiered host: DRAM, not DRAM + NVMe
    (None, 64.0, 64.0),    # no DRAM tier stat: fall back
    (0.0, 64.0, 64.0),     # DRAM tier stat present but 0: fall back
    (None, None, None),    # neither: no data, never a guess
])
def test_host_memory_is_dram_with_fallback(dram, provisioned, expected):
    stats = {}
    if dram is not None:
        stats[("h1", "mem:DRAM|memory_tier_total_capacity")] = dram
    if provisioned is not None:
        stats[("h1", "mem|host_provisioned")] = provisioned
    snap = traversal.ClusterSnapshot("c1", [("h1", "esx01")], {}, stats, {})
    assert traversal.host_memory_capacity_kb(snap, "h1") == expected


def test_overcommit_uses_native_allocation_stats_when_present():
    host = {**HOST_STATS, "cpu|vcpus_allocated_on_all_powered_on_vms": 8,
            "mem|memory_allocated_on_all_powered_on_vms": 16 * 1024 * 1024}
    snap, _ = snapshot_with({"vm-on": "Powered On", "vm-off": "Powered Off", "vm-unknown": None}, host)
    _, hosts = traversal.collect_cluster_and_host_metrics(snap)
    (_, _, h), = hosts
    assert h["host_cpu_overcommit_ratio"] == 8 / 16
    assert h["host_memory_overcommit_ratio"] == 16 / 64
