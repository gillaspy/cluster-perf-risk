"""2.0.4: Suite API failures are counted, and a total failure is reported on
the adapter instance instead of looking like a healthy, empty collection."""
from unittest import mock

import adapter
import pytest
import suite_api
from test_native_projection import CLUSTER_KEYS
from test_native_projection import CLUSTERS
from test_native_projection import HOST_KEYS
from test_native_projection import run_collect


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._body = body if body is not None else {}

    def json(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def client_returning(*responses):
    """A client whose get/post return the given responses (or raise them, if
    they are exceptions) in order."""
    queue = list(responses)

    def send(url, **kwargs):
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    c = mock.MagicMock()
    c.get.side_effect = send
    c.post.side_effect = send
    return c


@pytest.fixture(autouse=True)
def fresh_stats():
    suite_api.CALL_STATS.reset()
    yield


def stat_body(value):
    ts = suite_api.now_ms()
    return {"values": [{"stat-list": {"stat": [{"timestamps": [ts], "data": [value]}]}}]}


def test_successful_call_is_counted():
    c = client_returning(FakeResponse(200, stat_body(42.0)))
    assert suite_api.latest_stat(c, "r1", "cpu|x") == 42.0
    assert (suite_api.CALL_STATS.calls, suite_api.CALL_STATS.failures) == (1, 0)


def test_failed_call_is_no_data_and_counted():
    c = client_returning(FakeResponse(401), FakeResponse(500), FakeResponse(404))
    assert suite_api.latest_stat(c, "r1", "cpu|x") is None
    assert suite_api.get_property(c, "r1", "p") is None
    assert suite_api.fetch_children_of_kind(c, "r1", "VirtualMachine") == []
    assert (suite_api.CALL_STATS.calls, suite_api.CALL_STATS.failures) == (3, 3)


def test_exception_is_counted_and_reraised():
    c = client_returning(ConnectionError("down"))
    with pytest.raises(ConnectionError):
        suite_api.latest_stat(c, "r1", "cpu|x")
    assert (suite_api.CALL_STATS.calls, suite_api.CALL_STATS.failures) == (1, 1)


def resource(i):
    return {"identifier": f"id-{i}", "resourceKey": {"name": f"n{i}"}}


def test_resource_query_reads_every_page():
    size = suite_api.RESOURCE_QUERY_PAGE_SIZE
    page0 = {"pageInfo": {"totalCount": size + 1}, "resourceList": [resource(i) for i in range(size)]}
    page1 = {"pageInfo": {"totalCount": size + 1}, "resourceList": [resource(size)]}
    c = client_returning(FakeResponse(200, page0), FakeResponse(200, page1))
    got = suite_api.fetch_resources(c, "ClusterComputeResource", "VMWARE")
    assert len(got) == size + 1 and got[-1] == (f"id-{size}", f"n{size}")
    assert [call.kwargs["params"]["page"] for call in c.post.call_args_list] == [0, 1]
    assert suite_api.CALL_STATS.calls == 2


def test_failed_resource_query_raises_instead_of_returning_nothing():
    c = client_returning(FakeResponse(401))
    with pytest.raises(suite_api.SuiteApiError):
        suite_api.fetch_resources(c, "ClusterComputeResource", "VMWARE")


def error_of(res):
    return res.get_json().get("errorMessage")


def test_partial_failure_keeps_the_other_clusters_and_no_error():
    res = run_collect(fail_cluster="c-uuid-1")
    assert error_of(res) is None
    assert {o["key"]["name"] for o in res.get_json()["result"]} == {"cl02", "esx02"}


def test_all_clusters_failing_is_reported():
    def boom(client, cluster_id):
        raise RuntimeError("boom")

    with mock.patch.object(adapter.cluster, "gather_metric_values", side_effect=boom), \
         mock.patch.object(adapter, "fetch_resources", return_value=CLUSTERS), \
         mock.patch.object(adapter, "fetch_resource_keys", return_value={}):
        res = adapter.collect(_instance())
    assert "all 2 clusters" in error_of(res)


def test_failed_inventory_query_is_reported():
    with mock.patch.object(adapter, "fetch_resources", side_effect=suite_api.SuiteApiError("query failed")):
        res = adapter.collect(_instance())
    assert error_of(res).startswith("Suite API error: query failed")


def test_every_stats_call_failing_is_reported():
    def gather(client, cluster_id):
        # Simulates every per-cluster call coming back non-2xx.
        suite_api.CALL_STATS.calls += 3
        suite_api.CALL_STATS.failures += 3
        return {}

    def inventory(client, *args):
        suite_api.CALL_STATS.calls += 1
        return CLUSTERS

    def keys(client, kind, adapter_kind):
        suite_api.CALL_STATS.calls += 1
        return CLUSTER_KEYS if kind == "ClusterComputeResource" else HOST_KEYS

    with mock.patch.object(adapter, "fetch_resources", side_effect=inventory), \
         mock.patch.object(adapter, "fetch_resource_keys", side_effect=keys), \
         mock.patch.object(adapter.cluster, "gather_metric_values", side_effect=gather), \
         mock.patch.object(adapter, "collect_cluster_and_host_metrics", return_value=({}, [])):
        res = adapter.collect(_instance())
    assert "Every Suite API stats call failed (6 calls)" in error_of(res)


def test_counters_are_logged_at_info_each_cycle():
    with mock.patch.object(adapter.logger, "info") as info:
        run_collect()
    assert any("Suite API:" in str(c.args[0]) and "calls" in str(c.args[0]) for c in info.call_args_list)


def _instance():
    from test_native_projection import FakeInstance
    return FakeInstance()
