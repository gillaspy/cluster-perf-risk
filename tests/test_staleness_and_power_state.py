"""2.1.0 item 1: a stale stat is no data, and only powered-on VMs count."""
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


def stat_at(value, ts):
    return FakeResponse(200, {"values": [{"stat-list": {"stat": [{"timestamps": [ts], "data": [value]}]}}]})


def test_fresh_sample_is_its_value():
    c = client_returning(stat_at(7.0, NOW - 4 * MIN))
    assert suite_api.latest_stat(c, "r", "k") == 7.0
    assert suite_api.CALL_STATS.stale == 0


def test_stale_sample_is_no_data_and_counted():
    c = client_returning(stat_at(7.0, NOW - (STALE_AFTER_MINUTES + 6) * MIN))
    assert suite_api.latest_stat(c, "r", "k") is None
    assert suite_api.CALL_STATS.stale == 1


def test_stale_relative_to_newest_sample_even_if_clock_is_behind():
    # The collector's clock is 20 minutes behind VCF Operations; the second
    # sample is 11 minutes older than the newest one returned this cycle.
    with mock.patch.object(suite_api, "now_ms", return_value=NOW - 20 * MIN):
        c = client_returning(stat_at(1.0, NOW), stat_at(2.0, NOW - 11 * MIN))
        assert suite_api.latest_stat(c, "fresh", "k") == 1.0
        assert suite_api.latest_stat(c, "old", "k") is None


def test_collector_clock_a_few_minutes_ahead_is_tolerated():
    c = client_returning(stat_at(3.0, NOW - (STALE_AFTER_MINUTES + 4) * MIN))
    assert suite_api.latest_stat(c, "r", "k") == 3.0


def test_sample_without_timestamp_is_no_data():
    c = client_returning(FakeResponse(200, {"values": [{"stat-list": {"stat": [{"data": [5.0]}]}}]}))
    assert suite_api.latest_stat(c, "r", "k") is None


def test_powered_off_vm_is_excluded_everywhere():
    vms = {"vm-on": "Powered On", "vm-off": "Powered Off", "vm-unknown": None}
    vm_stats = {
        "vm-on": {"config|hardware|num_Cpu": 4, "mem|guest_provisioned": 4 * 1024 * 1024,
                  "cpu|20_sec_peak_readyPct": 1.0},
        # Huge and badly contended -- must not show up anywhere.
        "vm-off": {"config|hardware|num_Cpu": 64, "mem|guest_provisioned": 512 * 1024 * 1024,
                   "cpu|20_sec_peak_readyPct": 50.0},
        "vm-unknown": {"config|hardware|num_Cpu": 64, "cpu|20_sec_peak_readyPct": 40.0},
    }
    host_stats = {"hardware|cpuInfo|num_CpuCores": 16, "mem|host_provisioned": 64 * 1024 * 1024}

    def stat(client, rid, key):
        return (vm_stats.get(rid) or host_stats).get(key)

    def prop(client, rid, name):
        assert name == VM_POWER_STATE_PROPERTY
        return vms[rid]

    with mock.patch.object(traversal, "fetch_child_hosts", return_value=[("h1", "esx01")]), \
         mock.patch.object(traversal, "fetch_children_of_kind", return_value=[(v, v) for v in vms]), \
         mock.patch.object(traversal, "get_property", side_effect=prop), \
         mock.patch.object(traversal, "latest_stat", side_effect=stat):
        cluster, hosts = traversal.collect_cluster_and_host_metrics(None, "c1", 50)

    (_, _, h), = hosts
    assert cluster["worst_vcpu_ready_pct"] == 1.0 and cluster["p90_vcpu_ready_pct"] == 1.0
    assert h["host_cpu_overcommit_ratio"] == 4 / 16
    assert h["host_memory_overcommit_ratio"] == 4 / 64
    assert h["host_monster_vm_count"] == 0
    assert cluster["cluster_cpu_monster_vm_ratio"] == 0
    assert cluster["cluster_memory_monster_vm_ratio"] == 0
