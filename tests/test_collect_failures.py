"""A Suite API failure is a collection error, never a healthy empty run (#1)."""
from unittest import mock

import adapter
import constants_native as cn
from fake_suite_api import Estate
from fake_suite_api import FakeClient
from fake_suite_api import Instance
from fake_suite_api import rkey


def estate():
    return Estate(
        resources={
            "c1": rkey("cl01", "ClusterComputeResource", "domain-c1"),
            "c2": rkey("cl02", "ClusterComputeResource", "domain-c2"),
            "h1": rkey("esx01", "HostSystem", "host-1"),
            "h2": rkey("esx02", "HostSystem", "host-2"),
        },
        children={"c1": ["h1"], "c2": ["h2"]},
        stats={"h1": {"cpu|utilization_average": 10.0}, "h2": {"cpu|utilization_average": 20.0}},
        properties={},
    )


def collect(client):
    return adapter.collect(Instance(client)).get_json()


def test_no_token_is_an_error_and_nothing_else_is_called():
    client = FakeClient(estate(), token="")
    js = collect(client)
    assert "Could not get a Suite API token" in js["errorMessage"]
    assert client.calls == []


def test_refused_cluster_query_is_an_error_not_zero_clusters():
    js = collect(FakeClient(estate(), status={"/api/resources/query": 403}))
    assert "HTTP 403" in js["errorMessage"]
    assert not js.get("result")


def test_failed_bulk_read_is_an_error():
    js = collect(FakeClient(estate(), status={"/stats/latest/query": 500}))
    assert "Suite API call failed" in js["errorMessage"] and "HTTP 500" in js["errorMessage"]


def test_zero_clusters_from_a_good_query_is_a_clean_empty_result_with_a_warning(caplog):
    client = FakeClient(Estate({}, {}, {}, {}))
    js = collect(client)
    assert not js.get("errorMessage")
    assert "nothing to score" in caplog.text
    assert len(client.calls) == 1  # just the cluster query


def test_every_cluster_failing_is_an_error():
    with mock.patch.object(adapter.cluster, "gather_metric_values", side_effect=ValueError("bad payload")):
        js = collect(FakeClient(estate()))
    assert "Collection failed for all 2 clusters" in js["errorMessage"]
    assert "bad payload" in js["errorMessage"]


def test_vanished_resources_read_as_no_data_with_warnings(caplog):
    js = collect(FakeClient(estate(), status={"/stats/latest/query": 404}))
    assert not js.get("errorMessage")
    for o in js["result"]:
        props = {p["key"]: p["stringValue"] for p in o["properties"]}
        assert props[cn.COMPOSITE_BAND_ATTR] == "unknown"
    assert "returned 404 for a chunk of 2 resources" in caplog.text
    assert "No ClusterComputeResource stats came back for any of 2 resources" in caplog.text
    assert "No HostSystem stats came back for any of 2 resources" in caplog.text


def test_stats_that_come_back_empty_are_not_silent(caplog):
    e = estate()
    e.stats = {}
    js = collect(FakeClient(e))
    assert not js.get("errorMessage")
    assert "No HostSystem stats came back for any of 2 resources" in caplog.text
