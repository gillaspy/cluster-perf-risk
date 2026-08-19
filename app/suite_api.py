"""
Generic Suite API wrappers -- no object-type awareness, no risk-scoring logic.
Used by traversal.py and by cluster.py's cluster-only derived metrics.

NOTE: SuiteApiClient.query_for_resources() (a convenience method) discards
the internal resource UUID needed for subsequent stats/relationship calls,
so these helpers call the Suite API directly instead.
"""
from typing import Any
from typing import Optional

from aria.ops.suite_api_client import SuiteApiClient
from constants_shared import RESOURCE_KIND_HOST


def fetch_resources(
    client: SuiteApiClient, resource_kind: str, adapter_kind: str
) -> list[tuple[str, str]]:
    """Returns a list of (resource_id, resource_name) tuples."""
    response = client.paged_post(
        "/api/resources/query",
        "resourceList",
        json={"resourceKind": [resource_kind], "adapterKind": [adapter_kind]},
    )
    return [
        (entry["identifier"], entry["resourceKey"]["name"])
        for entry in response.get("resourceList", [])
    ]


def latest_stat(client: SuiteApiClient, resource_id: str, statkey: str) -> Optional[float]:
    """
    We only ever request a single statKey per call, so whatever comes back is
    the value we asked for -- even when VCF Operations auto-aggregates an
    instanced metric and renames the key with an instance prefix (e.g.
    disk:Aggregate of all instances|commandsAveraged_average instead of
    disk|commandsAveraged_average). Matching the returned key exactly against
    the requested key silently dropped those aggregated values.
    """
    with client.get(
        f"/api/resources/{resource_id}/stats/latest",
        params={"statKey": [statkey]},
    ) as response:
        if not response.ok:
            return None
        body: dict[str, Any] = response.json()
        for entry in body.get("values", []):
            for stat in entry.get("stat-list", {}).get("stat", []):
                data = stat.get("data", [])
                if data:
                    return data[-1]
    return None


def get_property(client: SuiteApiClient, resource_id: str, property_name: str) -> Optional[str]:
    """
    Resource PROPERTIES (config, inventory metadata) are a different endpoint
    and response shape from stats -- /api/resources/{id}/properties, not
    /stats/latest. Values come back as strings regardless of underlying type
    (e.g. "10000.0" for a numeric linkspeed), so callers must cast.
    """
    with client.get(f"/api/resources/{resource_id}/properties") as response:
        if not response.ok:
            return None
        body: dict[str, Any] = response.json()
        for prop in body.get("property", []):
            if prop.get("name") == property_name:
                return prop.get("value")
    return None


def fetch_children_of_kind(
    client: SuiteApiClient, resource_id: str, resource_kind: str
) -> list[tuple[str, str]]:
    """Returns (resource_id, resource_name) tuples of resource_id's direct children of the given kind."""
    with client.get(
        f"/api/resources/{resource_id}/relationships",
        params={"relationshipType": "CHILD"},
    ) as response:
        if not response.ok:
            return []
        body = response.json()
        return [
            (entry["identifier"], entry["resourceKey"]["name"])
            for entry in body.get("resourceList", [])
            if entry.get("resourceKey", {}).get("resourceKindKey") == resource_kind
        ]


def fetch_child_hosts(client: SuiteApiClient, cluster_id: str) -> list[tuple[str, str]]:
    """Returns (host_id, host_name) tuples of the cluster's direct HostSystem children."""
    return fetch_children_of_kind(client, cluster_id, RESOURCE_KIND_HOST)
