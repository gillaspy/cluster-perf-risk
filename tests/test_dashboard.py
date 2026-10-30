"""The shipped dashboard (2.1.1): colors come only from the two scoreboards,
by Risk Band Level with fixed bounds. There is no heatmap: it stretched its
colors over the values on screen, so a level-1 cluster could draw green."""
import json
import os

import pytest
from constants_native import COMPOSITE_BAND_LEVEL_ATTR
from constants_native import COMPOSITE_SCORE_ATTR

DASHBOARD = os.path.join(os.path.dirname(__file__), "..", "content", "dashboards", "cluster_performance_risk.json")
CLUSTER_KIND = "resourceKind:id:0_::_"
HOST_KIND = "resourceKind:id:1_::_"


@pytest.fixture(scope="module")
def db():
    return json.load(open(DASHBOARD))["dashboards"][0]


def widgets(db, kind):
    return [w for w in db["widgets"] if w["type"] == kind]


def by_title(db, title):
    (w,) = [w for w in db["widgets"] if w["config"]["title"] == title]
    return w


def test_no_heatmap(db):
    assert not widgets(db, "Heatmap")


def test_scoreboards_color_by_band_level_with_fixed_bounds(db):
    boards = widgets(db, "Scoreboard")
    assert len(boards) == 2
    for w in boards:
        for m in w["config"]["metric"]["resourceKindMetrics"]:
            assert m["metricKey"] == COMPOSITE_BAND_LEVEL_ATTR
            assert m["colorMethod"] == 0
            assert (m["yellowBound"], m["orangeBound"], m["redBound"]) == (1, 2, 3)


def test_nothing_colors_by_the_score(db):
    for w in widgets(db, "Scoreboard"):
        assert COMPOSITE_SCORE_ATTR not in json.dumps(w["config"])


def test_widget_titles_match(db):
    # The header shows the outer title; 2.1.0 left it at "Performance Risk %".
    for w in db["widgets"]:
        assert w["title"] == w["config"]["title"]


def test_cluster_scoreboard_shows_every_cluster(db):
    w = by_title(db, "Cluster Risk Band")
    assert w["config"]["selfProvider"] == {"selfProvider": True}
    assert {m["resourceKindId"] for m in w["config"]["metric"]["resourceKindMetrics"]} == {CLUSTER_KIND}


def test_cluster_list_drives_the_host_widgets(db):
    clusters = by_title(db, "Cluster Metrics")
    assert clusters["config"]["selfProvider"] == {"selfProvider": True}
    host_board = by_title(db, "Host Risk Band")
    assert {m["resourceKindId"] for m in host_board["config"]["metric"]["resourceKindMetrics"]} == {HOST_KIND}
    receivers = {i["widgetIdReceiver"] for i in db["widgetInteractions"] if i["widgetIdProvider"] == clusters["id"]}
    assert receivers == {by_title(db, "Hosts in Cluster")["id"], host_board["id"]}


def test_interactions_point_at_existing_widgets(db):
    ids = [w["id"] for w in db["widgets"]]
    assert len(ids) == len(set(ids))
    for i in db["widgetInteractions"]:
        assert i["widgetIdProvider"] in ids and i["widgetIdReceiver"] in ids


def test_lists_lead_with_the_band(db):
    for title in ("Cluster Metrics", "Hosts in Cluster"):
        names = [c["metricName"] for c in by_title(db, title)["config"]["additionalColumns"]]
        assert names[:4] == ["Risk Band", "Risk Band Level", "Metrics In Worst Band", "Risk Score"]


def test_layout_does_not_overlap(db):
    cells = set()
    for w in db["widgets"]:
        g = w["gridsterCoords"]
        for x in range(g["x"], g["x"] + g["w"]):
            for y in range(g["y"], g["y"] + g["h"]):
                assert (x, y) not in cells, w["config"]["title"]
                cells.add((x, y))
