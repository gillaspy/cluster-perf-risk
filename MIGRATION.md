# Migrating to 2.1.0

2.1.0 changes how risk is judged, so **some clusters and hosts change color
after the upgrade** without anything changing in your environment. No metric
is removed or renamed; the install is an in-place upgrade over 2.0.x.

## What changes color, and why
- **The composite band is now the worst sub-metric band.** One red
  sub-metric makes the object red; before, the band came from the score, and
  one red among greens showed yellow. Expect more objects in yellow, orange
  and red. The numeric `Risk Score` is calculated as before.
- **Thresholds changed:** P90 vCPU Co-Stop 1/2/4 -> 0.5/1/2; cluster Max Host
  Ballooned 1/1.25/2 -> 1/2/4; host Memory Overcommit Ratio 1/1.4/1.6 ->
  1/1.4/1.8; host CPU and Memory Reservation 40/60/80 -> 10/40/60. See
  [docs/METRICS.md](docs/METRICS.md#thresholds).
- **Powered-off VMs no longer count.** Their vCPUs and memory leave the
  overcommit ratios and monster VM counts, and their last stats leave the
  worst/P90 contention metrics. Hosts with many powered-off VMs improve.
- **Old stats are no data.** A stat more than 10 minutes behind the rest
  shows no value (band `unknown`) instead of its last value.
- **Host memory is DRAM.** On hosts with memory tiering, ballooned %, memory
  overcommit and memory monster VMs are now measured against DRAM only, not
  DRAM + NVMe. On a host whose NVMe tier is 4x its DRAM, memory overcommit
  rises about 5x. Hosts without tiering are unaffected.

## New attributes
On clusters and hosts: `Performance Risk|Composite|Risk Band Level` (the band
as 0 green to 3 red) and `Performance Risk|Composite|Metrics In Worst Band`.

## Your own content
- **Anything colored by `Risk Score` thresholds** (60/80/90, the old band
  limits) no longer matches the band: the score ranges of the bands overlap.
  Color by `Risk Band Level` (1 yellow, 2 orange, 3 red) or use the `Risk
  Band` property. The shipped "Cluster Performance Risk" dashboard does this
  already: its heatmap and scoreboard now color by `Risk Band Level`, and
  the scoreboard shows the level instead of the score. To get the new
  dashboard, reinstall the pak with "Reset Default Content" ticked, or
  import it from `content/dashboards/`.
- **Alerts or symptoms on `Risk Band` or on sub-metric bands** fire more
  often after the upgrade, for the reasons above.
- History is not recalculated: values before the upgrade keep the old rules.

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
longer updated.
