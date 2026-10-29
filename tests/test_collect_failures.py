"""A Suite API failure is a collection error, never a healthy empty run (#1)."""
from unittest import mock

import adapter
import constants_native as cn
from test_native_projection import CLUSTER_KEYS
from test_native_projection import HOST_KEYS


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body or {}

    def json(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeClient:
    """Answers the resource query from routes; records every call."""

    def __init__(self, token="t", query_status=200, clusters=None, hosts=None, get_status=200):
        self.token = ""
        self._token = token
        self.credential = mock.Mock(host="https://ops.example.test/suite-api/")
        self.query_status = query_status
        self.clusters = CLUSTER_KEYS if clusters is None else clusters
        self.hosts = HOST_KEYS if hosts is None else hosts
        self.get_status = get_status
        self.calls = []

    def _to_vrops_request(self, url, **kw):
        return kw

    def __enter__(self):
        self.token = self._token
        return self

    def __exit__(self, *a):
        self.token = ""

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        if self.query_status >= 400:
            return Resp(self.query_status)
        kind = kw["json"]["resourceKind"][0]
        keys = self.clusters if kind == "ClusterComputeResource" else self.hosts
        rl = [{"identifier": i, "resourceKey": k} for i, k in keys.items()]
        return Resp(body={"resourceList": rl, "pageInfo": {"totalCount": len(rl)}})

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return Resp(self.get_status, {})


class Instance:
    def __init__(self, client):
        self.client = client

    def get_suite_api_client(self):
        return self.client

    def get_identifier_value(self, key, default=None):
        return default


def test_no_token_is_an_error_and_nothing_else_is_called():
    client = FakeClient(token="")
    js = adapter.collect(Instance(client)).get_json()
    assert "Could not get a Suite API token" in js["errorMessage"]
    assert client.calls == []


def test_refused_cluster_query_is_an_error_not_zero_clusters():
    js = adapter.collect(Instance(FakeClient(query_status=403))).get_json()
    assert "HTTP 403" in js["errorMessage"]
    assert not js.get("result")


def test_zero_clusters_from_a_good_query_is_a_clean_empty_result_with_a_warning(caplog):
    js = adapter.collect(Instance(FakeClient(clusters={}, hosts={}))).get_json()
    assert not js.get("errorMessage")
    assert "nothing to score" in caplog.text


def test_every_cluster_failing_is_an_error():
    js = adapter.collect(Instance(FakeClient(get_status=500))).get_json()
    assert "Collection failed for all 2 clusters" in js["errorMessage"]
    assert "HTTP 500" in js["errorMessage"]


def test_a_vanished_resource_reads_as_no_data_not_a_failure():
    js = adapter.collect(Instance(FakeClient(get_status=404))).get_json()
    assert not js.get("errorMessage")
    for o in js["result"]:
        props = {p["key"]: p["stringValue"] for p in o["properties"]}
        assert props[cn.COMPOSITE_BAND_ATTR] == "unknown"
