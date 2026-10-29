"""
Generic Suite API wrappers -- no object-type awareness, no risk-scoring logic.
Used by traversal.py, which reads each cluster's data in bulk.

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
from constants_shared import CLOCK_SKEW_TOLERANCE_MINUTES
from constants_shared import RESOURCE_KIND_HOST
from constants_shared import STALE_AFTER_MINUTES

logger = logging.getLogger(__name__)

# Page size for /api/resources/query. Same as the SDK's own paged_post default.
RESOURCE_QUERY_PAGE_SIZE = 1000

# Most resource IDs sent in one stats/properties latest/query request. Larger
# sets are split into chunks of this size.
BULK_MAX_RESOURCE_IDS = 200

# The instance VCF Operations aggregates an instanced stat into, e.g.
# disk:Aggregate of all instances|commandsAveraged_average.
AGGREGATE_INSTANCE = "Aggregate of all instances"


class SuiteApiError(Exception):
    """A Suite API call whose failure must not be read as "no data", e.g. the
    resource inventory query: an empty cluster list from a failed query would
    otherwise report a successful collection of nothing."""


class CallStats:
    """HTTP calls made and failed in one collection cycle. A failure is a
    non-2xx response or an exception (connection error, timeout). Token
    requests made by the SDK client itself are not counted. `stale` counts
    stats that came back but were too old to use (see is_stale), and
    `newest_ms` is the newest sample timestamp VCF Operations returned this
    cycle, the reference for is_stale."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.calls = 0
        self.failures = 0
        self.stale = 0
        self.stale_keys: dict[str, int] = {}
        self.newest_ms = 0
        self.started = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def summary(self) -> str:
        return (
            f"Suite API: {self.calls} calls, {self.failures} failed, "
            f"{self.stale} stale, {self.elapsed():.1f}s"
        ) + (f" (stale: {self.stale_keys})" if self.stale_keys else "")

    def count_stale(self, statkey: str) -> None:
        self.stale += 1
        self.stale_keys[statkey] = self.stale_keys.get(statkey, 0) + 1


CALL_STATS = CallStats()


def now_ms() -> int:
    """The collector's clock, in ms. A function so tests can replace it."""
    return int(time.time() * 1000)


def is_stale(sample_ms: int, newest_ms: int) -> bool:
    """
    True when a sample is too old to use. Two checks:

    * Against the newest sample VCF Operations returned this cycle: older by
      more than STALE_AFTER_MINUTES is stale. Both timestamps come from VCF
      Operations, so the collector's clock plays no part. This catches what
      actually goes stale -- a powered-off VM, a disconnected host -- while
      everything else keeps updating.
    * Against the collector's clock, with CLOCK_SKEW_TOLERANCE_MINUTES of
      slack: catches the case the first cannot, where nothing is updating at
      all (the vCenter adapter stopped), so the newest sample is old too.
    """
    limit_ms = STALE_AFTER_MINUTES * 60_000
    if newest_ms - sample_ms > limit_ms:
        return True
    return now_ms() - sample_ms > limit_ms + CLOCK_SKEW_TOLERANCE_MINUTES * 60_000


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


def _fresh_value(statkey: str, value: float, timestamps: list) -> Optional[float]:
    """The value, or None when its sample is stale. A stat with no timestamp
    cannot be shown to be fresh, so it is no data too."""
    if not timestamps:
        CALL_STATS.count_stale(statkey)
        return None
    sample_ms = int(timestamps[-1])
    CALL_STATS.newest_ms = max(CALL_STATS.newest_ms, sample_ms)
    if is_stale(sample_ms, CALL_STATS.newest_ms):
        CALL_STATS.count_stale(statkey)
        return None
    return value


def _chunks(ids: list[str]) -> list[list[str]]:
    return [ids[i:i + BULK_MAX_RESOURCE_IDS] for i in range(0, len(ids), BULK_MAX_RESOURCE_IDS)]


def _aggregate_key(statkey: str) -> str:
    """group|metric -> group:Aggregate of all instances|metric."""
    group, sep, rest = statkey.partition("|")
    return f"{group}:{AGGREGATE_INSTANCE}{sep}{rest}" if sep else statkey


def _pick(returned: dict[str, Any], statkey: str) -> Optional[Any]:
    """The returned entry for a requested key. Asked for a stat, VCF
    Operations also returns every instance of it (cpu:26|utilization_average
    for thread 26), so only the requested key counts -- or, when the stat is
    only stored aggregated, its "Aggregate of all instances" instance, which
    is what the single-key GET returned (see latest_stat)."""
    if statkey in returned:
        return returned[statkey]
    return returned.get(_aggregate_key(statkey))


def bulk_latest_stats(
    client: SuiteApiClient, resource_ids: list[str], statkeys: list[str]
) -> dict[tuple[str, str], float]:
    """
    {(resource_id, statkey): value} for every requested stat that has a fresh
    latest sample, from POST /api/resources/stats/latest/query in chunks of
    BULK_MAX_RESOURCE_IDS. A failed chunk counts as a failure and its stats
    are missing (no data). Staleness is judged after every chunk is in, so
    the reference (the newest sample) covers the whole request.
    """
    samples: dict[tuple[str, str], tuple[float, list]] = {}
    for chunk in _chunks(resource_ids):
        body = _post(
            client,
            "/api/resources/stats/latest/query",
            json={"resourceId": chunk, "statKey": statkeys, "maxSamples": 1},
        )
        if body is None:
            continue
        for entry in body.get("values", []):
            returned = {}
            for stat in entry.get("stat-list", {}).get("stat", []):
                key = stat.get("statKey", {}).get("key")
                if key and stat.get("data"):
                    returned[key] = stat
            for statkey in statkeys:
                stat = _pick(returned, statkey)
                if stat is not None:
                    samples[(entry.get("resourceId"), statkey)] = (
                        stat["data"][-1], stat.get("timestamps", [])
                    )
    for _value, timestamps in samples.values():
        if timestamps:
            CALL_STATS.newest_ms = max(CALL_STATS.newest_ms, int(timestamps[-1]))
    fresh = {}
    for (resource_id, statkey), (value, timestamps) in samples.items():
        value = _fresh_value(statkey, value, timestamps)
        if value is not None:
            fresh[(resource_id, statkey)] = value
    return fresh


def bulk_latest_properties(
    client: SuiteApiClient, resource_ids: list[str], property_keys: list[str]
) -> dict[tuple[str, str], str]:
    """
    {(resource_id, property_key): value as a string} from POST
    /api/resources/properties/latest/query in chunks of BULK_MAX_RESOURCE_IDS.
    A text property comes back under "values", a number under "data"; both
    are returned as strings, like the per-resource properties GET, so callers
    cast. Properties are never stale (see STALE_AFTER_MINUTES).
    """
    found: dict[tuple[str, str], str] = {}
    for chunk in _chunks(resource_ids):
        body = _post(
            client,
            "/api/resources/properties/latest/query",
            json={"resourceIds": chunk, "propertyKeys": property_keys},
        )
        if body is None:
            continue
        for entry in body.get("values", []):
            contents = entry.get("property-contents", {}).get("property-content", [])
            for prop in contents:
                key = prop.get("statKey")
                if isinstance(key, dict):
                    key = key.get("key")
                if key not in property_keys:
                    continue
                values = prop.get("values") or prop.get("data") or []
                if values:
                    found[(entry.get("resourceId"), key)] = str(values[-1])
    return found


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
