"""
Generic Suite API wrappers -- no object-type awareness, no risk-scoring logic.
Used by snapshot.py and adapter.py.

NOTE: SuiteApiClient.query_for_resources() (a convenience method) discards
the internal resource UUID needed for subsequent stats/relationship calls,
so these helpers call the Suite API directly instead.

Reads are bulk calls (many resources and keys per request); snapshot.py
makes them once per collection cycle.

Failures raise SuiteApiError instead of returning an empty answer: the SDK's
paged_post() returns an empty list on a 401/403/5xx, which made a failed
login or query look like an environment with no clusters. A 404 from a
stats or properties query (none of the resources exist any more) still
reads as "no data".
"""
from contextlib import contextmanager
from typing import Any
from typing import Iterator

import aria.ops.adapter_logging as logging
from aria.ops.suite_api_client import SuiteApiClient

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


class SuiteApiError(Exception):
    """A Suite API call answered with an error status."""

    def __init__(self, method: str, url: str, status: int):
        hint = ""
        if status in (401, 403):
            hint = " (check that the Suite API account can read VMWARE objects)"
        super().__init__(f"{method} {url} returned HTTP {status}{hint}")
        self.status = status


def _check(response: Any, method: str, url: str) -> None:
    if not response.ok:
        raise SuiteApiError(method, url, response.status_code)


PAGE_SIZE = 1000


def _query_resources(client: SuiteApiClient, resource_kind: str, adapter_kind: str) -> list[dict[str, Any]]:
    """Every page of POST /api/resources/query. Pages itself rather than use
    paged_post(), which returns an empty list when the query fails."""
    url = "/api/resources/query"
    entries: list[dict[str, Any]] = []
    page = 0
    while True:
        with client.post(
            url,
            params={"page": page, "pageSize": PAGE_SIZE},
            json={"resourceKind": [resource_kind], "adapterKind": [adapter_kind]},
        ) as response:
            _check(response, "POST", url)
            body: dict[str, Any] = response.json()
        batch = body.get("resourceList", [])
        entries.extend(batch)
        total = int(body.get("pageInfo", {}).get("totalCount", len(entries)))
        page += 1
        if not batch or len(entries) >= total:
            return entries


def check_access(client: SuiteApiClient, resource_kind: str, adapter_kind: str) -> None:
    """One small query (a single resource of the kind), to prove the account
    can log in and read. Raises SuiteApiError if it cannot."""
    url = "/api/resources/query"
    with client.post(
        url,
        params={"page": 0, "pageSize": 1},
        json={"resourceKind": [resource_kind], "adapterKind": [adapter_kind]},
    ) as response:
        _check(response, "POST", url)


def fetch_resources(
    client: SuiteApiClient, resource_kind: str, adapter_kind: str
) -> dict[str, dict[str, Any]]:
    """Returns {resource_id: full Suite API resourceKey dict}, in query order.
    The resourceKey is used to build external (native) Objects with exactly
    the identity VCF Operations holds; its "name" is the resource name."""
    return {
        entry["identifier"]: entry["resourceKey"]
        for entry in _query_resources(client, resource_kind, adapter_kind)
        if "resourceKey" in entry
    }


def _chunks(ids: list[str], size: int = PAGE_SIZE) -> Iterator[list[str]]:
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def fetch_children(
    client: SuiteApiClient, parent_ids: list[str], child_kind: str
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, dict[str, Any]]]:
    """
    Direct children of the given kind for many parents at once
    (POST /api/resources/bulk/relationships). Returns
    ({parent_id: [(child_id, child_name), ...]}, {child_id: resourceKey}).
    Every parent_id is in the first dict, with [] when it has no children
    of that kind.
    """
    url = "/api/resources/bulk/relationships"
    children: dict[str, list[tuple[str, str]]] = {pid: [] for pid in parent_ids}
    keys: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(parent_ids):
        seen = 0
        page = 0
        while True:
            with client.post(
                url,
                params={"page": page, "pageSize": PAGE_SIZE},
                json={"relationshipType": "CHILD", "resourceIds": chunk},
            ) as response:
                _check(response, "POST", url)
                body: dict[str, Any] = response.json()
            batch = body.get("resourcesRelations", [])
            for relation in batch:
                resource = relation.get("resource", {})
                resource_key = resource.get("resourceKey", {})
                if resource_key.get("resourceKindKey") != child_kind:
                    continue
                child_id = resource["identifier"]
                keys[child_id] = resource_key
                for parent_id in relation.get("relatedResources", []):
                    if parent_id in children:
                        children[parent_id].append((child_id, resource_key["name"]))
            seen += len(batch)
            total = int(body.get("pageInfo", {}).get("totalCount", seen))
            page += 1
            if not batch or seen >= total:
                break
    return children, keys


def _base_key(statkey: str) -> str:
    """'disk:Aggregate of all instances|commandsAveraged_average' ->
    'disk|commandsAveraged_average'"""
    group, sep, rest = statkey.partition("|")
    return group.split(":", 1)[0] + sep + rest


def latest_stats(
    client: SuiteApiClient, resource_ids: list[str], statkeys: list[str]
) -> dict[tuple[str, str], float]:
    """
    Latest value of every statkey on every resource, 1000 resources per call
    (POST /api/resources/stats/latest/query). Returns
    {(resource_id, requested_statkey): value}; a stat with no data is absent.

    VCF Operations auto-aggregates an instanced metric and renames the key
    with an instance prefix (e.g. disk:Aggregate of all instances|
    commandsAveraged_average for disk|commandsAveraged_average), so a
    returned key is matched to the requested key it came from. As with one
    statKey per call, the first returned stat with data wins.
    """
    url = "/api/resources/stats/latest/query"
    wanted = set(statkeys)
    values: dict[tuple[str, str], float] = {}
    for chunk in _chunks(resource_ids):
        with client.post(url, json={"resourceId": chunk, "statKey": statkeys}) as response:
            if response.status_code == 404:
                logger.warning(
                    f"POST {url} returned 404 for a chunk of {len(chunk)} resources "
                    "(none of them exist any more); they read as no data"
                )
                continue
            _check(response, "POST", url)
            body: dict[str, Any] = response.json()
        for entry in body.get("values", []):
            resource_id = entry.get("resourceId")
            for stat in entry.get("stat-list", {}).get("stat", []):
                key = stat.get("statKey", {}).get("key", "")
                requested = key if key in wanted else _base_key(key)
                data = stat.get("data", [])
                if requested in wanted and data and (resource_id, requested) not in values:
                    values[(resource_id, requested)] = data[-1]
    return values


def latest_properties(
    client: SuiteApiClient, resource_ids: list[str], property_keys: list[str]
) -> dict[tuple[str, str], Any]:
    """
    Current value of every property key on every resource
    (POST /api/resources/properties/latest/query). Returns
    {(resource_id, property_key): value}. Values are strings for string
    properties and numbers for numeric ones (e.g. config|network|linkspeed
    may come back as 10000.0), so callers must cast.
    """
    url = "/api/resources/properties/latest/query"
    values: dict[tuple[str, str], Any] = {}
    for chunk in _chunks(resource_ids):
        with client.post(url, json={"resourceIds": chunk, "propertyKeys": property_keys}) as response:
            if response.status_code == 404:
                logger.warning(
                    f"POST {url} returned 404 for a chunk of {len(chunk)} resources "
                    "(none of them exist any more); they read as no data"
                )
                continue
            _check(response, "POST", url)
            body: dict[str, Any] = response.json()
        for entry in body.get("values", []):
            resource_id = entry.get("resourceId")
            for prop in entry.get("property-contents", {}).get("property-content", []):
                samples = prop.get("values") or prop.get("data") or []
                if samples:
                    values[(resource_id, prop.get("statKey"))] = samples[-1]
    return values
