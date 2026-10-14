"""Guardrail tests for the native-only output (v2.0.0)."""
import json
import os
import re
from unittest import mock

import adapter
import constants_host
import constants_native as cn
import pytest
from constants_cluster import BAND_PROPERTY_LABELS
from constants_cluster import NATIVE_STATKEY_MAP

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "fixtures")
DASHBOARD = os.path.join(HERE, "..", "content", "dashboards", "cluster_performance_risk.json")


def rkey(name, kind, objid, vcid):
    return {
        "name": name, "adapterKindKey": "VMWARE", "resourceKindKey": kind,
        "resourceIdentifiers": [
            {"identifierType": {"name": "VMEntityObjectID", "isPartOfUniqueness": True}, "value": objid},
            {"identifierType": {"name": "VMEntityVCID", "isPartOfUniqueness": True}, "value": vcid},
            {"identifierType": {"name": "VMEntityName", "isPartOfUniqueness": False}, "value": ""},
        ],
    }


CLUSTERS = [("c-uuid-1", "cl01"), ("c-uuid-2", "cl02")]
CLUSTER_KEYS = {"c-uuid-1": rkey("cl01", "ClusterComputeResource", "domain-c1", "vc1"),
                "c-uuid-2": rkey("cl02", "ClusterComputeResource", "domain-c1", "vc2")}
HOST_KEYS = {"h-uuid-1": rkey("esx01", "HostSystem", "host-1", "vc1"),
             "h-uuid-2": rkey("esx02", "HostSystem", "host-2", "vc2")}


class FakeInstance:
    def get_suite_api_client(self):
        c = mock.MagicMock()
        c.__enter__.return_value = c
        return c

    def get_identifier_value(self, key, default=None):
        return default


def run_collect(keys=True, fail_cluster=None):
    cm = {k: 1.0 for k in cn.CLUSTER_PROJECTION}
    hm = {k: 1.0 for k in cn.HOST_PROJECTION}

    def gather(client, cluster_id):
        if cluster_id == fail_cluster:
            raise RuntimeError("boom")
        return dict(cm)

    def traverse(client, cluster_id, thr):
        return {}, [("h-uuid-1", "esx01", dict(hm))] if cluster_id == "c-uuid-1" else [("h-uuid-2", "esx02", dict(hm))]

    def keys_for(client, kind, adapter_kind):
        if not keys:
            return {}
        return CLUSTER_KEYS if kind == "ClusterComputeResource" else HOST_KEYS

    with mock.patch.object(adapter, "fetch_resources", return_value=CLUSTERS), \
         mock.patch.object(adapter, "fetch_resource_keys", side_effect=keys_for), \
         mock.patch.object(adapter.cluster, "gather_metric_values", side_effect=gather), \
         mock.patch.object(adapter, "collect_cluster_and_host_metrics", side_effect=traverse):
        return adapter.collect(FakeInstance())


def test_pack_emits_no_objects_of_its_own_and_no_relationships():
    js = run_collect().get_json()
    kinds = {(o["key"]["adapterKind"], o["key"]["objectKind"]) for o in js["result"]}
    assert kinds == {("VMWARE", "ClusterComputeResource"), ("VMWARE", "HostSystem")}
    assert js["relationships"] == []
    assert len(js["result"]) == 4


def test_definition_has_no_object_types_and_no_flag():
    d = adapter.get_adapter_definition().to_json()
    assert not d.get("object_types")
    assert {i["key"] for i in d["adapter_instance"]["identifiers"]} == {
        "container_memory_limit", "monster_vm_threshold_pct"}


def test_external_objects_carry_only_prefixed_attributes_and_exact_counts():
    js = run_collect().get_json()
    for o in js["result"]:
        names = [m["key"] for m in o["metrics"]] + [p["key"] for p in o["properties"]]
        assert names and all(n.startswith(cn.NATIVE_ROOT + "|") for n in names)
        assert len(names) == len(set(names))
        expected = 2 * len(cn.CLUSTER_PROJECTION) + 2 if o["key"]["objectKind"] == "ClusterComputeResource" \
            else 2 * len(cn.HOST_PROJECTION) + 2
        assert len(names) == expected
        assert not o.get("events")
    cl = next(o for o in js["result"] if o["key"]["name"] == "cl01")
    assert {i["key"]: i["value"] for i in cl["key"]["identifiers"]} == {
        "VMEntityObjectID": "domain-c1", "VMEntityVCID": "vc1", "VMEntityName": ""}


def test_one_failing_cluster_does_not_lose_the_others():
    js = run_collect(fail_cluster="c-uuid-1").get_json()
    assert {o["key"]["name"] for o in js["result"]} == {"cl02", "esx02"}


def test_no_native_match_emits_nothing_and_does_not_crash():
    res = run_collect(keys=False)
    assert res.get_json()["result"] == []


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


def test_unique_within_each_scope():
    for mapping in (cn.CLUSTER_PROJECTION, cn.HOST_PROJECTION):
        names = [cn.metric_attr(*v) for v in mapping.values()]
        assert len(names) == len(set(names))


def test_every_scored_metric_is_mapped():
    assert set(cn.CLUSTER_PROJECTION) == {k[len("band_"):] for k in BAND_PROPERTY_LABELS}
    assert set(cn.HOST_PROJECTION) == {k[len("band_"):] for k in constants_host.HOST_BAND_PROPERTY_LABELS}


def test_no_collision_with_native_statkeys():
    assert not set(all_attr_names()) & set(NATIVE_STATKEY_MAP)
    for fname in ("host_statkeys.json", "cluster_statkeys.json"):
        path = os.path.join(FIXTURES, fname)
        if not os.path.exists(path):
            pytest.skip(f"{fname} fixture not present (copy native catalog to tests/fixtures/)")
        raw = open(path).read()
        assert not any(n in raw for n in all_attr_names())


def test_dashboard_only_references_native_kinds_and_known_attributes():
    d = json.load(open(DASHBOARD))
    s = json.dumps(d)
    assert "cluster_perf_risk" not in s and "host_perf_risk" not in s
    assert {k["resourceKindKey"] for k in d["entries"]["resourceKind"]} == {"ClusterComputeResource", "HostSystem"}
    assert d["entries"]["resource"] == []
    valid = set(all_attr_names())
    used = set(re.findall(r'"metricKey": "([^"]+)"', s))
    assert used and used <= valid, used - valid
    db = d["dashboards"][0]
    ids = {w["id"] for w in db["widgets"]}
    assert all(i["widgetIdProvider"] in ids and i["widgetIdReceiver"] in ids for i in db["widgetInteractions"])
