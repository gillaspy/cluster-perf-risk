# Migrating to 2.0.0

2.0.0 removes the pack's own object types (`cluster_perf_risk`,
`host_perf_risk`) and the `publish_to_native_objects` parameter. The pack now
always writes its values onto the native vSphere cluster and host objects
under `Performance Risk|<Group>|<Label>` (see `docs/METRICS.md`).

## What breaks
Anything you built on the old objects or their metric keys stops receiving
data: custom dashboards, views, reports, super metrics, alerts, groups. The
shipped dashboard is replaced (same dashboard ID and name) by one built on the
native objects. Rebuild your own content on `ClusterComputeResource` /
`HostSystem` and the `Performance Risk|...` attributes.

## Upgrade steps
1. Before upgrading, note anything of yours that references the old objects.
2. Install the 2.0.0 pak (Administration > Integrations > Repository).
3. After the next collection, confirm `Performance Risk` appears under a
   cluster's and a host's metrics and properties.
4. Old `... - Perf Risk` objects stay in inventory with stale data until you
   delete them (Environment > Inventory, kind "vSphere Cluster Performance
   Risk" / "ESXi Performance Risk") or they age out. Delete them once nothing
   uses them.
5. Check the dashboard "Cluster Performance Risk". If the old copy is still
   listed beside the new one, delete the old one.

## Rolling back
Reinstall the 1.3.0 pak. Attributes already written to native objects remain
as history but are no longer updated.
