"""
Everything one collection cycle reads from VCF Operations, fetched in bulk
up front: the clusters' hosts, the hosts' VMs, and the latest value of every
statkey and property the scoring uses.

Reading one statkey of one resource per call cost about 12 calls per
cluster, 18 per host and 6 per VM each cycle: 779 Suite API calls and about
a minute for a 3-cluster, 9-host lab (2026-10-28). Read in bulk, the same
lab takes 9 calls (token acquire and release included); a larger estate
adds one call per further 1000 resources of a kind and per further 1000
relationships. With the per-request timeouts in suite_api.py, a cycle is
bounded by calls x 135 s. cluster.py and traversal.py compute exactly as
before, from this snapshot instead of from per-resource calls; the same lab
gave identical values both ways on VCF Operations 8.18, 9.0 and 9.1.

The trade: a failed bulk read fails the whole collection (with the call and
status), where one failed per-resource read used to lose just that value,
silently.

Every statkey and property read anywhere must be listed below for its
resource kind; Snapshot.stat() and Snapshot.property() raise if asked for
one that was not fetched, so a new metric cannot silently read as "no
data".
"""
from __future__ import annotations

from typing import Any
from typing import Optional

import aria.ops.adapter_logging as logging
from aria.ops.suite_api_client import SuiteApiClient
from constants_cluster import CLUSTER_LEVEL_METRICS
from constants_cluster import HOST_LINKSPEED_PROPERTY
from constants_cluster import NATIVE_STATKEY_MAP
from constants_cluster import NETWORK_USAGE_AVERAGE_STATKEY
from constants_cluster import NUMBER_VMOTION_STATKEY
from constants_cluster import VM_COUNT_PER_HOST_STATKEY
from constants_host import HOST_CPU_CAPACITY_STATKEY
from constants_host import HOST_CPU_RESERVED_STATKEY
from constants_host import HOST_MEMORY_RESERVED_PCT_STATKEY
from constants_host import HOST_MEMORY_USAGE_STATKEY
from constants_shared import CPU_UTILIZATION_STATKEY
from constants_shared import HOST_CPU_CORES_STATKEY
from constants_shared import HOST_DROPPED_PACKETS_STATKEY
from constants_shared import HOST_MEMORY_CONTENTION_STATKEY
from constants_shared import MEMORY_BALLOON_KB_STATKEY
from constants_shared import MEMORY_TOTAL_CAPACITY_KB_STATKEY
from constants_shared import RESOURCE_KIND_CLUSTER
from constants_shared import RESOURCE_KIND_HOST
from constants_shared import RESOURCE_KIND_VM
from constants_shared import VM_LEVEL_STATKEYS
from constants_shared import VM_MEMORY_KB_STATKEY
from constants_shared import VM_NUM_CPU_STATKEY
from suite_api import fetch_children
from suite_api import latest_properties
from suite_api import latest_stats


logger = logging.getLogger(__name__)


def _unique(keys: list[str]) -> list[str]:
    return list(dict.fromkeys(keys))


STATKEYS = {
    # cluster.py: the cluster-level NATIVE_STATKEY_MAP metrics and vMotion %.
    RESOURCE_KIND_CLUSTER: _unique(
        [statkey for metric, statkey in NATIVE_STATKEY_MAP.items() if metric in CLUSTER_LEVEL_METRICS]
        + [VM_COUNT_PER_HOST_STATKEY, NUMBER_VMOTION_STATKEY]
    ),
    # cluster.py's "highest across hosts" metrics and traversal.py's per-host reads.
    RESOURCE_KIND_HOST: _unique(
        [statkey for metric, statkey in NATIVE_STATKEY_MAP.items() if metric not in CLUSTER_LEVEL_METRICS]
        + [
            MEMORY_BALLOON_KB_STATKEY,
            MEMORY_TOTAL_CAPACITY_KB_STATKEY,
            NETWORK_USAGE_AVERAGE_STATKEY,
            HOST_CPU_CORES_STATKEY,
            HOST_MEMORY_CONTENTION_STATKEY,
            HOST_DROPPED_PACKETS_STATKEY,
            CPU_UTILIZATION_STATKEY,
            HOST_MEMORY_USAGE_STATKEY,
            HOST_MEMORY_RESERVED_PCT_STATKEY,
            HOST_CPU_RESERVED_STATKEY,
            HOST_CPU_CAPACITY_STATKEY,
        ]
    ),
    # traversal.py's per-VM reads.
    RESOURCE_KIND_VM: _unique([VM_NUM_CPU_STATKEY, VM_MEMORY_KB_STATKEY, *VM_LEVEL_STATKEYS.values()]),
}

PROPERTY_KEYS = {
    RESOURCE_KIND_HOST: [HOST_LINKSPEED_PROPERTY],
}


class Snapshot:
    def __init__(
        self,
        hosts_by_cluster: dict[str, list[tuple[str, str]]],
        vms_by_host: dict[str, list[tuple[str, str]]],
        host_keys: dict[str, dict[str, Any]],
        kinds: dict[str, str],
        stats: dict[tuple[str, str], float],
        properties: dict[tuple[str, str], Any],
    ):
        self._hosts_by_cluster = hosts_by_cluster
        self._vms_by_host = vms_by_host
        self._host_keys = host_keys
        self._kinds = kinds
        self._stats = stats
        self._properties = properties

    def child_hosts(self, cluster_id: str) -> list[tuple[str, str]]:
        """(host_id, host_name) of the cluster's direct HostSystem children."""
        return self._hosts_by_cluster.get(cluster_id, [])

    def child_vms(self, host_id: str) -> list[tuple[str, str]]:
        """(vm_id, vm_name) of the host's direct VirtualMachine children."""
        return self._vms_by_host.get(host_id, [])

    def host_key(self, host_id: str) -> Optional[dict[str, Any]]:
        """The host's Suite API resourceKey, from the relationships read."""
        return self._host_keys.get(host_id)

    def stat(self, resource_id: str, statkey: str) -> Optional[float]:
        """Latest value, or None when the resource has no data for it."""
        kind = self._kinds.get(resource_id)
        if statkey not in STATKEYS.get(kind, []):
            raise KeyError(f"{statkey!r} is not read for {kind}; add it to snapshot.STATKEYS")
        return self._stats.get((resource_id, statkey))

    def property(self, resource_id: str, property_key: str) -> Optional[Any]:
        """Current value (string or number), or None."""
        kind = self._kinds.get(resource_id)
        if property_key not in PROPERTY_KEYS.get(kind, []):
            raise KeyError(f"{property_key!r} is not read for {kind}; add it to snapshot.PROPERTY_KEYS")
        return self._properties.get((resource_id, property_key))


def read(client: SuiteApiClient, cluster_ids: list[str]) -> Snapshot:
    """Reads everything for these clusters. Raises SuiteApiError on any failed call."""
    hosts_by_cluster, host_keys = fetch_children(client, cluster_ids, RESOURCE_KIND_HOST)
    host_ids = _unique([host_id for hosts in hosts_by_cluster.values() for host_id, _name in hosts])
    vms_by_host, _vm_keys = fetch_children(client, host_ids, RESOURCE_KIND_VM)
    vm_ids = _unique([vm_id for vms in vms_by_host.values() for vm_id, _name in vms])

    kinds = {
        **{vm_id: RESOURCE_KIND_VM for vm_id in vm_ids},
        **{host_id: RESOURCE_KIND_HOST for host_id in host_ids},
        **{cluster_id: RESOURCE_KIND_CLUSTER for cluster_id in cluster_ids},
    }
    stats: dict[tuple[str, str], float] = {}
    for kind, ids in ((RESOURCE_KIND_CLUSTER, cluster_ids), (RESOURCE_KIND_HOST, host_ids), (RESOURCE_KIND_VM, vm_ids)):
        if ids:
            kind_stats = latest_stats(client, ids, STATKEYS[kind])
            if not kind_stats:
                # Every value of this kind will read as unknown; say why.
                logger.warning(
                    f"No {kind} stats came back for any of {len(ids)} resources; "
                    "their metrics read as unknown this cycle"
                )
            stats.update(kind_stats)
    properties = (
        latest_properties(client, host_ids, PROPERTY_KEYS[RESOURCE_KIND_HOST]) if host_ids else {}
    )
    return Snapshot(hosts_by_cluster, vms_by_host, host_keys, kinds, stats, properties)
