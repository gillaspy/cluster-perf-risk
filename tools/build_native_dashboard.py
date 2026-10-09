#!/usr/bin/env python3
"""
Derive the native-object dashboard (content/dashboards/cluster_performance_risk_v2.json)
from the original own-object dashboard. Re-run after changing the mapping in
app/constants_native.py. Does not modify the original dashboard file.

Needs publish_to_native_objects=true on the adapter instance (the attributes
only exist on VMWARE objects when it is on).
"""
import copy
import json
import os
import sys
import uuid

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "app"))
import constants_native as cn  # noqa: E402
from constants_cluster import METRIC_COMPOSITE_SCORE  # noqa: E402
from constants_host import HOST_METRIC_COMPOSITE_SCORE  # noqa: E402

SRC = os.path.join(ROOT, "content/dashboards/cluster_performance_risk.json")
DST = os.path.join(ROOT, "content/dashboards/cluster_performance_risk_v2.json")

CLUSTER_KIND_ID = "resourceKind:id:0_::_"
HOST_KIND_ID = "resourceKind:id:1_::_"
NEW_NAME = "Cluster Performance Risk (Native)"


def native_key(old_key, mapping, composite_key):
    if old_key == composite_key:
        return cn.COMPOSITE_SCORE_ATTR
    group, label = mapping[old_key]
    return cn.metric_attr(group, label)


def short(key):  # display name = last path segment
    return key.rsplit("|", 1)[-1]


def group_by(kind, text):
    return {
        "resourceKind": kind, "adapterKind": "VMWARE",
        "typeId": CLUSTER_KIND_ID if kind == "ClusterComputeResource" else HOST_KIND_ID,
        "id": f"004null0020{len('VMWARE'):02d}VMWARE{kind}",
        "text": text, "type": "resourceKind", "parentText": "vCenter", "parentId": "VMWARE",
    }


def tag_filter(kind_id):
    return {"path": [f"/source/kind/kind:{kind_id}"],
            "value": {"bus": [], "adapterKind": [], "kind": [kind_id], "exclaim": False,
                      "healthRange": [], "maintenanceSchedule": [], "adapterInstance": [],
                      "collector": [], "tier": [], "state": [], "tag": [], "day": [], "status": []}}


def columns(cols, mapping, composite_key, kind_id):
    return [{"boxLabel": "", "metricName": short(native_key(c["metricKey"], mapping, composite_key)),
             "metricKey": native_key(c["metricKey"], mapping, composite_key),
             "resourceKindId": kind_id} for c in cols]


def main():
    d = json.load(open(SRC))
    out = copy.deepcopy(d)
    out["uuid"] = str(uuid.uuid4())
    out["entries"] = {
        "resourceKind": [
            {"resourceKindKey": "ClusterComputeResource", "internalId": CLUSTER_KIND_ID, "adapterKindKey": "VMWARE"},
            {"resourceKindKey": "HostSystem", "internalId": HOST_KIND_ID, "adapterKindKey": "VMWARE"},
        ],
        "resource": [],  # no pinned objects: nothing environment-specific in the file
    }
    db = out["dashboards"][0]
    old_dash_id = db["id"]
    db["id"] = str(uuid.uuid4())
    db["name"] = NEW_NAME
    idmap = {w["id"]: str(uuid.uuid4()) for w in db["widgets"]}
    for w in db["widgets"]:
        w["id"] = idmap[w["id"]]
        w.pop("states", None)  # saved grid layouts are keyed by old dashboard/widget ids
        c = w["config"]
        if w["type"] == "Heatmap":
            c["mode"] = "all"
            c["resource"] = []
            cl, ho = c["configs"]
            cl["colorBy"] = {"metricKey": cn.COMPOSITE_SCORE_ATTR, "value": cn.COMPOSITE_SCORE_ATTR}
            cl["groupBy"] = group_by("ClusterComputeResource", "Cluster Compute Resource")
            cl["resourceKind"] = CLUSTER_KIND_ID
            ho["colorBy"] = {"metricKey": cn.COMPOSITE_SCORE_ATTR, "value": cn.COMPOSITE_SCORE_ATTR}
            ho["groupBy"] = group_by("HostSystem", "Host System")
            ho["resourceKind"] = HOST_KIND_ID
        elif w["type"] == "Scoreboard":
            c["resource"] = []
            c["selfProvider"] = {"selfProvider": False}  # shows the object selected in the Heatmap
            for m, (name, kid) in zip(c["metric"]["resourceKindMetrics"],
                                      [("Cluster Compute Resource", CLUSTER_KIND_ID), ("Host System", HOST_KIND_ID)]):
                m["metricKey"] = cn.COMPOSITE_SCORE_ATTR
                m["metricName"] = short(cn.COMPOSITE_SCORE_ATTR)
                m["resourceKindName"] = name
                m["resourceKindId"] = kid
        elif w["title"] == "Cluster Metrics":
            c["resource"] = []
            c["additionalColumns"] = columns(c["additionalColumns"], cn.CLUSTER_PROJECTION,
                                             METRIC_COMPOSITE_SCORE, CLUSTER_KIND_ID)
            c["tagFilter"] = tag_filter(CLUSTER_KIND_ID)
        elif w["title"] == "Hosts in Cluster":
            c["resource"] = []
            c["additionalColumns"] = columns(c["additionalColumns"], cn.HOST_PROJECTION,
                                             HOST_METRIC_COMPOSITE_SCORE, HOST_KIND_ID)
            c["tagFilter"] = tag_filter(HOST_KIND_ID)
        else:
            raise SystemExit(f"unexpected widget {w['title']}")
    for i in db["widgetInteractions"]:
        i["widgetIdProvider"] = idmap[i["widgetIdProvider"]]
        i["widgetIdReceiver"] = idmap[i["widgetIdReceiver"]]
    json.dump(out, open(DST, "w"), indent=2)
    open(DST, "a").write("\n")
    print(f"wrote {DST} (old dashboard {old_dash_id} -> {db['id']})")


if __name__ == "__main__":
    main()
