"""Collection Health: a cycle's warnings are visible on the adapter instance
object itself (Collection Health|Warnings in Last Cycle,
Collection Health|First Warning), not only in adapter.log."""
import logging

import adapter
import collection_health
from test_native_projection import run_collect


def health_object(js):
    return next(o for o in js["result"] if o["key"]["objectKind"] == "adapter_instance")


def attrs(obj):
    return {m["key"]: m["numberValue"] for m in obj["metrics"]} | \
           {p["key"]: p["stringValue"] for p in obj["properties"]}


def test_a_clean_cycle_has_zero_warnings_and_no_first_warning():
    js = run_collect().get_json()
    a = attrs(health_object(js))
    assert a["Collection Health|Warnings in Last Cycle"] == 0
    assert "Collection Health|First Warning" not in a


def test_warnings_are_counted_and_the_first_one_is_kept():
    js = run_collect(fail_cluster="c-uuid-1").get_json()
    a = attrs(health_object(js))
    assert a["Collection Health|Warnings in Last Cycle"] >= 1
    assert "Collection Health|First Warning" in a


def test_a_hard_error_is_visible_through_the_error_message_not_collection_health():
    # CollectResult.get_json() returns only {"errorMessage": ...} once
    # with_error() is called -- every object, Collection Health included, is
    # dropped. That is fine: the error message is already the account's
    # visibility mechanism for a total failure; Collection Health exists for
    # the partial, non-fatal case that would otherwise only show in
    # adapter.log (see test_warnings_are_counted_and_the_first_one_is_kept).
    from test_native_projection import FakeInstance

    class NoClient(FakeInstance):
        def get_suite_api_client(self):
            return None

    js = adapter.collect(NoClient()).get_json()
    assert js["errorMessage"]
    assert "result" not in js


def test_handler_is_removed_after_the_block_even_on_exception():
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        with collection_health.CollectionHealth():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert root.handlers == before


def test_counts_only_warning_and_above():
    with collection_health.CollectionHealth() as health:
        logging.getLogger("x").info("not counted")
        logging.getLogger("x").warning("first")
        logging.getLogger("x").error("second")
    assert health.count == 2
    assert health.first == "first"
