"""Test Connection checks what it can (#8)."""
import adapter
import cluster
import host
import scoring
from fake_suite_api import Estate
from fake_suite_api import FakeClient
from fake_suite_api import rkey


class Instance:
    def __init__(self, client=None, **identifiers):
        self.client = client
        self.identifiers = {"container_memory_limit": "1024", **identifiers}

    def get_suite_api_client(self):
        return self.client

    def get_identifier_value(self, key, default=None):
        return self.identifiers.get(key, default)


def test_valid_parameters_pass_without_a_client():
    assert adapter.test(Instance()).get_json() == {}


def test_bad_threshold_and_memory_limit_fail():
    err = adapter.test(Instance(monster_vm_threshold_pct="abc", container_memory_limit="0")).get_json()["errorMessage"]
    assert "Monster VM Threshold" in err and "'abc'" in err
    assert "Memory Limit" in err
    assert "Monster VM Threshold" in adapter.test(Instance(monster_vm_threshold_pct="150")).get_json()["errorMessage"]
    assert "Monster VM Threshold" in adapter.test(Instance(monster_vm_threshold_pct="0")).get_json()["errorMessage"]


def test_shipped_threshold_tables_are_sound():
    assert scoring.table_problems(cluster.BAND_BOUNDS, cluster.WEIGHTS) == []
    assert scoring.table_problems(host.BAND_BOUNDS, host.WEIGHTS) == []


def test_broken_threshold_table_is_reported():
    problems = scoring.table_problems({"m": {"green_max": 5, "yellow_max": 1, "orange_max": 9}}, {"m": 0})
    assert len(problems) == 2


def test_with_a_client_it_logs_in_and_runs_one_query():
    client = FakeClient(Estate({}, {}, {}, {}))
    assert adapter.test(Instance(client)).get_json() == {}
    assert [(url, kw["params"]["pageSize"]) for url, kw in client.calls] == [("/api/resources/query", 1)]


def test_with_a_client_a_refused_login_or_query_fails():
    assert "token" in adapter.test(Instance(FakeClient(Estate({}, {}, {}, {}), token=""))).get_json()["errorMessage"]
    client = FakeClient(Estate({}, {}, {}, {}), status={"/api/resources/query": 403})
    assert "HTTP 403" in adapter.test(Instance(client)).get_json()["errorMessage"]


def test_collect_falls_back_to_the_default_for_an_out_of_range_threshold(caplog):
    from unittest import mock

    seen = []

    def traverse(cycle, cluster_id, threshold):
        seen.append(threshold)
        return {}, []

    client = FakeClient(Estate({"c1": rkey("cl01", "ClusterComputeResource", "domain-c1")}, {}, {}, {}))
    with mock.patch.object(adapter, "collect_cluster_and_host_metrics", side_effect=traverse):
        for value in ("150", "0", "abc"):
            adapter.collect(Instance(client, monster_vm_threshold_pct=value))
        adapter.collect(Instance(client, monster_vm_threshold_pct="75"))
    assert seen == [50, 50, 50, 75.0]
    assert "'150' (must be a number from 1 to 100), falling back to the default, 50" in caplog.text
