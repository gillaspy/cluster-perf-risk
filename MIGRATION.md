# Migrating to 2.0.0

2.0.0 removes the pack's own object types (`cluster_perf_risk`,
`host_perf_risk`) and the `publish_to_native_objects` parameter. The pack now
always writes its values onto the native vSphere cluster and host objects
under `Performance Risk|<Group>|<Label>` (see `docs/METRICS.md`).

## What breaks
Anything you built on the old objects or their metric keys stops receiving
data: custom dashboards, views, reports, super metrics, alerts, groups. The
shipped dashboard "Cluster Performance Risk" is replaced by a new one of the
same name built on the native objects. Rebuild your own content on
`ClusterComputeResource` / `HostSystem` and the `Performance Risk|...` attributes.

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
3. Delete the 1.x dashboards that uninstalling leaves behind: "Cluster
   Performance Risk" and, if you installed 1.3.0, "Cluster Performance Risk
   (Native)" (Dashboards > Manage). The old "Cluster Performance Risk" points
   at the removed object types and shows unconfigured widgets; if it is still
   there, it can hide the new dashboard of the same name.
4. Install the 2.0.0 pak from the same page.
5. Recreate the adapter account under Integrations > Accounts.
6. After the next collection, confirm `Performance Risk` appears under a
   cluster's and a host's metrics and properties.
7. Check Environment > Inventory for leftover "vSphere Cluster Performance
   Risk" / "ESXi Performance Risk" objects and delete any that remain.
8. Open "Cluster Performance Risk" and click a cluster in the Heatmap. If its
   widgets say they are not configured, it is the old copy: delete it, then
   reinstall the 2.0.0 pak with "Install the PAK file even if it is already
   installed" and "Reset Default Content" ticked.

## Rolling back
Uninstall 2.0.0, install the 1.3.0 pak and recreate the adapter account.
Attributes already written to native objects remain as history but are no
longer updated. The `... Band` and `Risk Band` properties keep their last
value on the native objects (see "Removing the pack" in the README).
