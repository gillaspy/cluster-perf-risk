"""
Makes a cycle's warnings visible without adapter.log: every WARNING+ record
logged while collecting is counted, and the first one is kept. adapter.py
publishes them as Collection Health|Warnings in Last Cycle (a metric) and
Collection Health|First Warning (a property) on the adapter instance object
itself -- this adapter owns no VMWARE object to publish them on, but
AdapterInstance is itself a real, identified Object (see
aria.ops.adapter_instance.AdapterInstance), so nothing new needs to be
defined to write onto it.

Matches the Collection Health properties published by Iwan Rahabok's
e1-rahabok/VCF-vCommunity-Adapter (on its own vCenter object, which it owns;
we publish the same idea on the adapter instance, which we do).
"""
from __future__ import annotations

import logging


class _CountingHandler(logging.Handler):
    def __init__(self, health: "CollectionHealth") -> None:
        super().__init__(level=logging.WARNING)
        self._health = health

    def emit(self, record: logging.LogRecord) -> None:
        self._health.count += 1
        if self._health.first is None:
            self._health.first = record.getMessage()


class CollectionHealth:
    """Use as `with CollectionHealth() as health:` around one collection
    cycle. `health.count` and `health.first` (None if there were none) are
    valid once the block exits -- including when it exits via an exception,
    so a cycle that fails outright still reports what led up to it."""

    def __init__(self) -> None:
        self.count = 0
        self.first: str | None = None
        self._handler = _CountingHandler(self)

    def __enter__(self) -> "CollectionHealth":
        logging.getLogger().addHandler(self._handler)
        return self

    def __exit__(self, *exc_info: object) -> None:
        logging.getLogger().removeHandler(self._handler)
