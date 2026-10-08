"""Guardrail tests for the Phase 1 native projection (v1.2.0)."""
import json
import os
from contextlib import contextmanager
from unittest import mock

import adapter
import constants_native as cn
import pytest
from constants_cluster import BAND_PROPERTY_LABELS
from constants_cluster import METRIC_COMPOSITE_SCORE
from constants_cluster import NATIVE_STATKEY_MAP

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

CL_KEY = {
    "name": "cl01", "adapterKindKey": "VMWARE", "resourceKindKey": "ClusterComputeResource",
    "resourceIdentifiers": [
        {"identifierType": {"name": "VMEntityObjectID", "isPartOfUniqueness": True}, "value": "domain-c1"},
        {"identifierType": {"name": "VMEntityVCID", "isPartOfUniqueness": True}, "value": "vc-uuid"},
    ],
}
HOST_KEY = {
    "name": "esx01", "adapterKindKey": "VMWARE", "resourceKindKey": "HostSystem",
    "resourceIdentifiers": [
        {"identifierType": {"name": "VMEntityObjectID", "isPartOfUniqueness": True}, "value": "host-9"},
        {"identifierType": {"name": "VMEntityVCID", "isPartOfUniqueness": True}, "value": "vc-uuid"},
    ],
}


class FakeInstance:
    def __init__(self, flag):
        self.flag = flag

    def get_suite_api_client(self):
        @contextmanager
        def ctx():
            yield

        c = mock.MagicMock()
        c.__enter__.return_value = c
        return c

    def get_identifier_value(self, key, default=None):
        if key == cn.PARAM_PUBLISH_TO_NATIVE:
            return self.flag if self.flag is not None else default
        return default


def run_collect(flag, hosts=True, keys=True):
    cm = {k: 1.0 for k in cn.CLUSTER_PROJECTION}
    hm = {k: 1.0 for k in cn.HOST_PROJECTION}
    records = [("host-uuid-1", "esx01", hm)] if hosts else []
    with mock.patch.object(adapter, "fetch_resources", return_value=[("cl-uuid", "cl01")]), \
         mock.patch.object(adapter, "fetch_resource_keys",
                           side_effect=lambda c, kind, a: {} if not keys else ({"cl-uuid": CL_KEY} if kind == "ClusterComputeResource" else {"host-uuid-1": HOST_KEY})), \
         mock.patch.object(adapter.cluster, "gather_metric_values", return_value=dict(cm)), \
         mock.patch.object(adapter, "collect_cluster_and_host_metrics", return_value=({}, records)):
        return adapter.collect(FakeInstance(flag))


def strip_ts(obj):
    def drop(x):
        if isinstance(x, dict):
            return {k: drop(v) for k, v in x.items() if k != "timestamp"}
        if isinstance(x, list):
            return [drop(v) for v in x]
        return x
    return json.dumps(drop(obj), sort_keys=True)


def own_json(result):
    js = result.get_json()
    return [o for o in js["result"] if o["key"]["adapterKind"] == "ClusterPerfRisk"], js


def test_flag_off_has_no_external_objects_and_own_relationships_only():
    for flag in (None, "false"):
        res = run_collect(flag)
        js = res.get_json()
        assert {o["key"]["adapterKind"] for o in js["result"]} == {"ClusterPerfRisk"}
        assert all(r["parent"]["adapterKind"] == "ClusterPerfRisk" for r in js["relationships"])
        assert len(js["relationships"]) >= 1


def test_flag_on_own_objects_identical_to_flag_off():
    off, _ = own_json(run_collect("false"))
    on, _ = own_json(run_collect("true"))
    assert strip_ts(off) == strip_ts(on)


def test_flag_on_external_objects_only_carry_prefixed_attributes():
    _, js = own_json(run_collect("true"))
    ext = [o for o in js["result"] if o["key"]["adapterKind"] == "VMWARE"]
    assert {o["key"]["objectKind"] for o in ext} == {"ClusterComputeResource", "HostSystem"}
    for o in ext:
        names = [m["key"] for m in o["metrics"]] + [p["key"] for p in o["properties"]]
        assert names and all(n.startswith(cn.NATIVE_ROOT + "|") for n in names)
        assert o["events"] == [] if "events" in o else True
    # identity comes verbatim from the Suite API resourceKey
    cl = next(o for o in ext if o["key"]["objectKind"] == "ClusterComputeResource")
    assert cl["key"]["name"] == "cl01"
    assert {i["key"]: i["value"] for i in cl["key"]["identifiers"]} == {
        "VMEntityObjectID": "domain-c1", "VMEntityVCID": "vc-uuid"}


def test_flag_on_relationships_never_parented_by_native_objects():
    _, js = own_json(run_collect("true"))
    assert js["relationships"], "cluster->host relationship must still be emitted"
    assert all(r["parent"]["adapterKind"] == "ClusterPerfRisk" for r in js["relationships"])


def test_cluster_without_native_match_keeps_own_objects():
    res = run_collect("true", hosts=True, keys=False)
    own, js = own_json(res)
    assert len(own) == 2
    assert all(o["key"]["adapterKind"] == "ClusterPerfRisk" for o in js["result"])
    assert js["relationships"]


def all_attr_names():
    names = []
    for mapping in (cn.CLUSTER_PROJECTION, cn.HOST_PROJECTION):
        for group, label in mapping.values():
            names += [cn.metric_attr(group, label), cn.band_attr(group, label)]
    names += [cn.COMPOSITE_SCORE_ATTR, cn.COMPOSITE_BAND_ATTR]
    return names


def test_prefix_and_forbidden_roots():
    for n in all_attr_names():
        assert n.startswith("Performance Risk|")
        assert not any(n.startswith(r) for r in cn.FORBIDDEN_ROOTS)
        assert n.count("|") == 2


def test_unique_within_each_object_type():
    for mapping in (cn.CLUSTER_PROJECTION, cn.HOST_PROJECTION):
        names = [cn.metric_attr(*v) for v in mapping.values()]
        assert len(names) == len(set(names))


def test_every_own_metric_is_mapped():
    import constants_host
    assert set(cn.CLUSTER_PROJECTION) == set(k[len("band_"):] for k in BAND_PROPERTY_LABELS)
    assert set(cn.HOST_PROJECTION) == set(k[len("band_"):] for k in constants_host.HOST_BAND_PROPERTY_LABELS)


def test_no_collision_with_native_statkeys():
    names = set(all_attr_names()) | set(NATIVE_STATKEY_MAP)
    assert len(names) == len(set(all_attr_names())) + len(set(NATIVE_STATKEY_MAP) - set(all_attr_names()))
    for fname in ("host_statkeys.json", "cluster_statkeys.json"):
        path = os.path.join(FIXTURES, fname)
        if not os.path.exists(path):
            pytest.skip(f"{fname} fixture not present (copy native catalog to tests/fixtures/)")
        raw = open(path).read()
        assert not any(n in raw for n in all_attr_names())
