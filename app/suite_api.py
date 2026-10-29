"""
Generic Suite API wrappers -- no object-type awareness, no risk-scoring logic.
Used by traversal.py and by cluster.py's cluster-only derived metrics.

NOTE: SuiteApiClient.query_for_resources() (a convenience method) discards
the internal resource UUID needed for subsequent stats/relationship calls,
so these helpers call the Suite API directly instead.

Every HTTP call goes through _get() / _post() below, which count it in
CALL_STATS. A failed call used to return None silently, the same as "no
data", so a broken collection looked like a healthy one; the counters let
adapter.collect() report it instead.
"""
import math
import time
from typing import Any
from typing import Optional

import aria.ops.adapter_logging as logging
from aria.ops.suite_api_client import SuiteApiClient
from constants_shared import RESOURCE_KIND_HOST

logger = logging.getLogger(__name__)

# Page size for /api/resources/query. Same as the SDK's own paged_post default.
RESOURCE_QUERY_PAGE_SIZE = 1000


class SuiteApiError(Exception):
    """A Suite API call whose failure must not be read as "no data", e.g. the
    resource inventory query: an empty cluster list from a failed query would
    otherwise report a successful collection of nothing."""


class CallStats:
    """HTTP calls made and failed in one collection cycle. A failure is a
    non-2xx response or an exception (connection error, timeout). Token
    requests made by the SDK client itself are not counted."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.calls = 0
        self.failures = 0
        self.started = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def summary(self) -> str:
        return (
            f"Suite API: {self.calls} calls, {self.failures} failed, "
            f"{self.elapsed():.1f}s"
        )


CALL_STATS = CallStats()


def _request(client: SuiteApiClient, method: str, url: str, **kwargs: Any) -> Optional[Any]:
    """Sends one request and returns its JSON body, or None if it failed.
    Exceptions are counted and re-raised, so the caller's error isolation
    (per cluster in adapter.collect) still applies. Only the method, path and
    status are logged -- never headers, which carry the token."""
    CALL_STATS.calls += 1
    send = client.get if method == "GET" else client.post
    try:
        with send(url, **kwargs) as response:
            if not response.ok:
                CALL_STATS.failures += 1
                logger.warning(f"Suite API {method} {url} failed: HTTP {response.status_code}")
                return None
            return response.json()
    except Exception:
        CALL_STATS.failures += 1
        logger.warning(f"Suite API {method} {url} raised an exception")
        raise


def _get(client: SuiteApiClient, url: str, **kwargs: Any) -> Optional[Any]:
    return _request(client, "GET", url, **kwargs)


def _post(client: SuiteApiClient, url: str, **kwargs: Any) -> Optional[Any]:
    return _request(client, "POST", url, **kwargs)


def _query_resources(
    client: SuiteApiClient, resource_kind: str, adapter_kind: str
) -> list[dict[str, Any]]:
    """All pages of /api/resources/query. Paged here rather than with the
    SDK's paged_post(), which returns an empty list when a page fails and so
    cannot tell "no resources" from "the query failed". Raises SuiteApiError
    on any failed page."""
    query = {"resourceKind": [resource_kind], "adapterKind": [adapter_kind]}
    resources: list[dict[str, Any]] = []
    page = 0
    pages = 1
    while page < pages:
        body = _post(
            client,
            "/api/resources/query",
            params={"page": page, "pageSize": RESOURCE_QUERY_PAGE_SIZE},
            json=query,
        )
        if body is None:
            raise SuiteApiError(
                f"Resource query for {adapter_kind}:{resource_kind} failed (page {page})"
            )
        resources.extend(body.get("resourceList", []))
        total = int(body.get("pageInfo", {}).get("totalCount", len(resources)))
        pages = max(1, math.ceil(total / RESOURCE_QUERY_PAGE_SIZE))
        page += 1
    return resources


def fetch_resources(
    client: SuiteApiClient, resource_kind: str, adapter_kind: str
) -> list[tuple[str, str]]:
    """Returns a list of (resource_id, resource_name) tuples."""
    return [
        (entry["identifier"], entry["resourceKey"]["name"])
        for entry in _query_resources(client, resource_kind, adapter_kind)
    ]


def fetch_resource_keys(
    client: SuiteApiClient, resource_kind: str, adapter_kind: str
) -> dict[str, dict[str, Any]]:
    """Returns {resource_id: full Suite API resourceKey dict}. Used to build
    external (native) Objects with exactly the identity VCF Operations holds."""
    return {
        entry["identifier"]: entry["resourceKey"]
        for entry in _query_resources(client, resource_kind, adapter_kind)
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
    body = _get(
        client,
        f"/api/resources/{resource_id}/stats/latest",
        params={"statKey": [statkey]},
    )
    if body is None:
        return None
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
    body = _get(client, f"/api/resources/{resource_id}/properties")
    if body is None:
        return None
    for prop in body.get("property", []):
        if prop.get("name") == property_name:
            return prop.get("value")
    return None


def fetch_children_of_kind(
    client: SuiteApiClient, resource_id: str, resource_kind: str
) -> list[tuple[str, str]]:
    """Returns (resource_id, resource_name) tuples of resource_id's direct children of the given kind."""
    body = _get(
        client,
        f"/api/resources/{resource_id}/relationships",
        params={"relationshipType": "CHILD"},
    )
    if body is None:
        return []
    return [
        (entry["identifier"], entry["resourceKey"]["name"])
        for entry in body.get("resourceList", [])
        if entry.get("resourceKey", {}).get("resourceKindKey") == resource_kind
    ]


def fetch_child_hosts(client: SuiteApiClient, cluster_id: str) -> list[tuple[str, str]]:
    """Returns (host_id, host_name) tuples of the cluster's direct HostSystem children."""
    return fetch_children_of_kind(client, cluster_id, RESOURCE_KIND_HOST)
