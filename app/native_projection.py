"""
Phase 1 native-object projection. Writes the risk values onto existing VMWARE
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
    own_obj: Object,
    metric_values: dict[str, Optional[float]],
    mapping: dict[str, tuple[str, str]],
    composite_keys: tuple[str, str],
) -> int:
    """Copy values already computed for own_obj onto the native object. Returns attribute count."""
    target = native_object(result, resource_key)
    if target is None:
        return 0
    count = 0
    for key, (group, label) in mapping.items():
        value = metric_values.get(key)
        if value is not None:
            target.with_metric(metric_attr(group, label), value)
            count += 1
        band = own_obj.get_last_property_value(f"band_{key}")
        if band is not None:
            target.with_property(band_attr(group, label), band)
            count += 1
    score_key, band_key = composite_keys
    score = own_obj.get_last_metric_value(score_key)
    if score is not None:
        target.with_metric(COMPOSITE_SCORE_ATTR, score)
        count += 1
    band = own_obj.get_last_property_value(band_key)
    if band is not None:
        target.with_property(COMPOSITE_BAND_ATTR, band)
        count += 1
    return count
