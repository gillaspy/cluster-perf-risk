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

## Uninstall 1.x first
2.0.0 cannot be installed over 1.x. VCF Operations refuses an upgrade that
removes object types while objects of those types exist, and the install fails
at "Applied Adapter" with "Adapter install failed". The analytics log shows:

    Describe would remove resources, so we are failing to describe.
    Problematic resource kind is ClusterPerfRisk:cluster_perf_risk.

Uninstalling 1.x removes its adapter account and the old `... - Perf Risk`
objects, including their history. The adapter has no credentials, so
recreating the account only takes a name, a collector and, if you changed it,
the Monster VM Threshold.

## Upgrade steps
1. Note anything of yours that references the old objects, and the adapter
   account's settings (name, collector, Monster VM Threshold).
2. Uninstall 1.x: Administration > Integrations > Repository, the pack's
   ⋮ menu > Uninstall.
3. Install the 2.0.0 pak from the same page.
4. Recreate the adapter account under Integrations > Accounts.
5. After the next collection, confirm `Performance Risk` appears under a
   cluster's and a host's metrics and properties.
6. Check Environment > Inventory for leftover "vSphere Cluster Performance
   Risk" / "ESXi Performance Risk" objects and delete any that remain.
7. Check the dashboard "Cluster Performance Risk". If an old copy is still
   listed beside the new one, delete the old one.

## Rolling back
Uninstall 2.0.0, install the 1.3.0 pak and recreate the adapter account.
Attributes already written to native objects remain as history but are no
longer updated.
