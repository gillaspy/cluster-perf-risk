"""
Generic Suite API wrappers -- no object-type awareness, no risk-scoring logic.
Used by traversal.py and by cluster.py's cluster-only derived metrics.

NOTE: SuiteApiClient.query_for_resources() (a convenience method) discards
the internal resource UUID needed for subsequent stats/relationship calls,
so these helpers call the Suite API directly instead.
"""
from contextlib import contextmanager
from typing import Any
from typing import Iterator
from typing import Optional

import aria.ops.adapter_logging as logging
from aria.ops.suite_api_client import SuiteApiClient
from constants_shared import RESOURCE_KIND_HOST

logger = logging.getLogger(__name__)

# (connect, read) timeout in seconds for every Suite API request. The SDK
# client sets none, and neither does the Cloud Proxy for a collection, so
# without one a hung VCF Operations node holds the collection, and the
# session token, until the process is killed.
REQUEST_TIMEOUT = (15, 120)


def apply_request_timeout(client: SuiteApiClient, timeout: tuple = REQUEST_TIMEOUT) -> SuiteApiClient:
    """
    Gives every request this client sends a timeout, unless the call passes
    its own. Hooks SuiteApiClient._to_vrops_request (lib 1.1.x), the one
    place every request goes through, because the SDK sends its own token
    acquire and release requests and offers no other way to give those a
    timeout.
    """
    to_request = client._to_vrops_request

    def with_timeout(url: str, **kwargs: Any) -> dict:
        kwargs.setdefault("timeout", timeout)
        return to_request(url, **kwargs)

    client._to_vrops_request = with_timeout
    return client


@contextmanager
def session(client: SuiteApiClient) -> Iterator[SuiteApiClient]:
    """
    Same as `with client:` (acquire the token on entry, release it on exit),
    except that a failed release is logged instead of raised: once the reads
    have succeeded, a release that times out must not throw the collection
    away. The token then expires on the server.
    """
    client.__enter__()
    try:
        yield client
    finally:
        try:
            client.__exit__(None, None, None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not release the Suite API token: {e!r}")


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


def fetch_resource_keys(
    client: SuiteApiClient, resource_kind: str, adapter_kind: str
) -> dict[str, dict[str, Any]]:
    """Returns {resource_id: full Suite API resourceKey dict}. Used to build
    external (native) Objects with exactly the identity VCF Operations holds."""
    response = client.paged_post(
        "/api/resources/query",
        "resourceList",
        json={"resourceKind": [resource_kind], "adapterKind": [adapter_kind]},
    )
    return {
        entry["identifier"]: entry["resourceKey"]
        for entry in response.get("resourceList", [])
        if "resourceKey" in entry
    }


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
