"""Bulk Suite API reads (#6): a cycle is a fixed handful of calls and the
values are the same formulas as before."""
import adapter
import constants_cluster as cc
import constants_host as ch
import constants_native as cn
import constants_shared as cs
import pytest
import snapshot
import suite_api
from fake_suite_api import Estate
from fake_suite_api import FakeClient
from fake_suite_api import Instance
from fake_suite_api import Resp
from fake_suite_api import rkey

AGG = "disk:Aggregate of all instances|commandsAveraged_average"


def host_stats(cpu, iops, balloon, net_kbps, contention, dropped):
    return {
        "cpu|utilization_average": cpu, AGG: iops, "mem|vmmemctl_average": balloon,
        "mem|host_provisioned": 100000.0, "net|usage_average": net_kbps,
        "hardware|cpuInfo|num_CpuCores": 16.0, "mem|host_contentionPct": contention,
        "net|droppedPct": dropped, "mem|usage_average": 50.0, "mem|reservedCapacityPct": 10.0,
        "cpu|reservedCapacity_average": 1000.0, "cpu|capacity_provisioned": 40000.0,
    }


def vm_stats(vcpu, mem_kb, ready):
    return {
        "config|hardware|num_Cpu": vcpu, "mem|guest_provisioned": mem_kb,
        "cpu|20_sec_peak_readyPct": ready, "cpu|20_sec_peak_costopPct": 0.0,
        "mem|20_sec_peak_host_contentionPct": 0.0,
        "virtualDisk:scsi0:0|20_sec_peak_totalLatency_average": 5.0,
    }


def lab():
    return Estate(
        resources={
            "c1": rkey("cl01", "ClusterComputeResource", "domain-c1"),
            "h1": rkey("esx01", "HostSystem", "host-1"),
            "h2": rkey("esx02", "HostSystem", "host-2"),
            "rp1": rkey("Resources", "ResourcePool", "resgroup-1"),
            "vm1": rkey("vm1", "VirtualMachine", "vm-1"),
            "vm2": rkey("vm2", "VirtualMachine", "vm-2"),
            "vm3": rkey("vm3", "VirtualMachine", "vm-3"),
        },
        children={"c1": ["h1", "rp1", "h2"], "h1": ["vm1", "vm2"], "h2": ["vm3"]},
        stats={
            "c1": {
                "clusterServices|total_imbalance": 2000.0, "cpu|vcpus_to_cores_allocation_ratio": 1.5,
                "mem|virtual_to_physical_memory_allocation_ratio": 0.8,
                "summary|vm_count_per_host": 1.5, "summary|number_vmotion": 3.0,
            },
            "h1": host_stats(40.0, 100.0, 0.0, 12500.0, 0.1, 0.0),
            "h2": host_stats(60.0, 300.0, 1000.0, 25000.0, 0.3, 0.1),
            "vm1": vm_stats(4.0, 8000.0, 2.0),
            "vm2": vm_stats(10.0, 1000.0, 6.0),   # CPU monster: 10 > 50% of 16 cores
            "vm3": vm_stats(2.0, 60000.0, 1.0),   # memory monster: 60000 > 50% of 100000 KB
        },
        properties={"h1": {"config|network|linkspeed": "10000.0"}, "h2": {"config|network|linkspeed": 10000.0}},
    )


def metrics_of(js, name):
    o = next(o for o in js["result"] if o["key"]["name"] == name)
    return {m["key"]: m["numberValue"] for m in o["metrics"]}


def attr(mapping, key):
    return cn.metric_attr(*mapping[key])


def test_a_cycle_is_seven_bulk_calls_and_no_per_resource_gets():
    client = FakeClient(lab())
    js = adapter.collect(Instance(client)).get_json()
    assert not js.get("errorMessage")
    assert [url for url, _ in client.calls] == [
        "/api/resources/query",
        "/api/resources/bulk/relationships",
        "/api/resources/bulk/relationships",
        "/api/resources/stats/latest/query",
        "/api/resources/stats/latest/query",
        "/api/resources/stats/latest/query",
        "/api/resources/properties/latest/query",
    ]


def test_cluster_values():
    m = metrics_of(adapter.collect(Instance(FakeClient(lab()))).get_json(), "cl01")
    C = cn.CLUSTER_PROJECTION
    assert m[attr(C, cc.METRIC_CPU_THREAD_UTILIZATION)] == 60.0
    assert m[attr(C, cc.METRIC_DISK_IOPS)] == 300.0  # matched through the instanced aggregate key
    assert m[attr(C, cc.METRIC_HOST_CPU_IMBALANCE)] == 10.0  # pstdev(40, 60)
    assert m[attr(C, cc.METRIC_MEMORY_BALLOONED)] == 1.0
    assert m[attr(C, cc.METRIC_NETWORK_THROUGHPUT)] == pytest.approx(2.0)  # 200 Mbps of 10000
    assert m[attr(C, cc.METRIC_CLUSTER_CPU_IMBALANCE)] == 2.0
    assert m[attr(C, cc.METRIC_VMOTION_PCT)] == 100.0  # 3 / (1.5 * 2 hosts)
    assert m[attr(C, cc.METRIC_CLUSTER_CPU_MONSTER_VM_RATIO)] == 0.5
    assert m[attr(C, cc.METRIC_CLUSTER_MEMORY_MONSTER_VM_RATIO)] == 0.5
    assert m[attr(C, cs.METRIC_WORST_VCPU_READY)] == 6.0
    assert m[attr(C, cs.METRIC_WORST_DISK_LATENCY)] == 5.0
    assert m[attr(C, cs.METRIC_HOST_MEMORY_CONTENTION)] == 0.3


def test_host_values():
    m = metrics_of(adapter.collect(Instance(FakeClient(lab()))).get_json(), "esx01")
    H = cn.HOST_PROJECTION
    assert m[attr(H, ch.HOST_METRIC_CPU_THREAD_UTILIZATION)] == 40.0
    assert m[attr(H, ch.HOST_METRIC_CPU_OVERCOMMIT_RATIO)] == (4.0 + 10.0) / 16.0
    assert m[attr(H, ch.HOST_METRIC_MONSTER_VM_COUNT)] == 1
    assert m[attr(H, ch.HOST_METRIC_CPU_RESERVATION)] == 2.5
    assert m[attr(H, cs.METRIC_WORST_VCPU_READY)] == 6.0


def test_stats_are_chunked_at_1000_resources():
    calls = []

    class C:
        def post(self, url, **kw):
            calls.append(kw["json"]["resourceId"])
            return Resp(body={"values": []})

    suite_api.latest_stats(C(), [f"id-{i}" for i in range(2500)], ["a|b"])
    assert [len(c) for c in calls] == [1000, 1000, 500]


def test_first_stat_with_data_wins_and_exact_keys_match():
    body = {"values": [{"resourceId": "r", "stat-list": {"stat": [
        {"statKey": {"key": "a:inst0|x"}, "data": []},
        {"statKey": {"key": "a:Aggregate of all instances|x"}, "data": [1.0, 7.0]},
        {"statKey": {"key": "a:inst1|x"}, "data": [9.0]},
        {"statKey": {"key": "b|y"}, "data": [3.0]},
    ]}}]}

    class C:
        def post(self, url, **kw):
            return Resp(body=body)

    assert suite_api.latest_stats(C(), ["r"], ["a|x", "b|y"]) == {("r", "a|x"): 7.0, ("r", "b|y"): 3.0}


def test_relationship_pages_are_all_read():
    pages = [
        {"resourcesRelations": [{"resource": {"identifier": "h1", "resourceKey": rkey("esx01", "HostSystem", "host-1")},
                                 "relatedResources": ["c1"]}], "pageInfo": {"totalCount": 2}},
        {"resourcesRelations": [{"resource": {"identifier": "h2", "resourceKey": rkey("esx02", "HostSystem", "host-2")},
                                 "relatedResources": ["c1"]}], "pageInfo": {"totalCount": 2}},
    ]

    class C:
        def post(self, url, **kw):
            return Resp(body=pages[kw["params"]["page"]])

    children, keys = suite_api.fetch_children(C(), ["c1", "c2"], "HostSystem")
    assert children == {"c1": [("h1", "esx01"), ("h2", "esx02")], "c2": []}
    assert set(keys) == {"h1", "h2"}


def test_snapshot_refuses_a_key_it_did_not_read():
    snap = snapshot.Snapshot({}, {}, {}, {"h1": "HostSystem"}, {}, {})
    assert snap.stat("h1", "cpu|utilization_average") is None
    with pytest.raises(KeyError):
        snap.stat("h1", "cpu|not_fetched")
    with pytest.raises(KeyError):
        snap.property("h1", "config|not_fetched")
