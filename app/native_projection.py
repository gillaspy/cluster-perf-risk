"""
Native-object projection. Writes the risk values onto existing VMWARE
ClusterComputeResource / HostSystem objects as attributes under
"Performance Risk|<Group>|<Label>". Never touches a native statkey: the root is
unique to this pack (see constants_native.py guardrails).

External-object identity comes from the Suite API resourceKey (never
hand-built); if a resourceKey is missing/malformed the object is skipped and
logged, never guessed.
"""
from __future__ import annotations

from typing import Any
from typing import Optional

import aria.ops.adapter_logging as logging
from aria.ops.object import Identifier
from aria.ops.object import Object
from aria.ops.result import CollectResult
from constants_native import COMPOSITE_BAND_ATTR
from constants_native import COMPOSITE_SCORE_ATTR
from constants_native import band_attr
from constants_native import metric_attr

logger = logging.getLogger(__name__)


def native_object(result: CollectResult, resource_key: Optional[dict[str, Any]]) -> Optional[Object]:
    """Get-or-create the external Object matching a Suite API resourceKey."""
    try:
        identifiers = [
            Identifier(
                ident["identifierType"]["name"],
                str(ident["value"]),
                is_part_of_uniqueness=bool(ident["identifierType"].get("isPartOfUniqueness", True)),
            )
            for ident in resource_key.get("resourceIdentifiers", [])
        ]
        return result.object(
            resource_key["adapterKindKey"],
            resource_key["resourceKindKey"],
            resource_key["name"],
            identifiers=identifiers,
        )
    except (AttributeError, KeyError, TypeError) as e:
        logger.warning(f"Skipping native projection, unusable resourceKey {resource_key!r}: {e!r}")
        return None


def project(
    result: CollectResult,
    resource_key: Optional[dict[str, Any]],
    metric_values: dict[str, Optional[float]],
    scored: tuple,
    mapping: dict[str, tuple[str, str]],
) -> int:
    """
    Write metric_values plus their bands and the composite onto the native
    object. `scored` is (composite_score, composite_band, {metric_key: band})
    from cluster.score() / host.score(). Returns the attribute count (0 when
    the native object could not be identified).
    """
    target = native_object(result, resource_key)
    if target is None:
        return 0
    composite_score, composite_band, per_metric_band = scored
    count = 0
    for key, (group, label) in mapping.items():
        if key not in metric_values:
            continue
        value = metric_values[key]
        if value is not None:
            target.with_metric(metric_attr(group, label), value)
            count += 1
        target.with_property(band_attr(group, label), per_metric_band.get(key, "unknown"))
        count += 1
    target.with_metric(COMPOSITE_SCORE_ATTR, composite_score)
    target.with_property(COMPOSITE_BAND_ATTR, composite_band)
    return count + 2
