# Migrating to 2.1.1

2.1.1 changes only the shipped "Cluster Performance Risk" dashboard and the
docs. The adapter, metrics and thresholds are the same as 2.1.0.

## What changes on the dashboard
- **The heatmap is gone.** It stretched its colors over the values on
  screen, so its colors were relative: in 2.1.0 a yellow cluster could draw
  green. The 2.0.x heatmap did the same with the score.
- **Colors come from two scoreboards** with fixed bounds on `Risk Band
  Level`: 0 green, 1 yellow, 2 orange, 3 red.
  - **Cluster Risk Band**: every cluster, no selection needed.
  - **Host Risk Band**: the hosts of the cluster selected in Cluster
    Metrics.
- **Cluster Metrics lists every cluster** and drives the two host widgets.
  Both lists start with Risk Band, Risk Band Level, Metrics In Worst Band
  and Risk Score.

## Getting the new dashboard
**Delete the old dashboard first.** On the lab (VCF Operations 9.x, which
has no "Reset Default Content" option), installing the pak over an existing
"Cluster Performance Risk" left every widget unconfigured: lists showing
every object, empty scoreboards, an hourglass on each widget title.
Installing after deleting it worked.
1. Dashboards > Manage: delete "Cluster Performance Risk" (every copy, if
   there are several). Opening it afterwards from Recents or a bookmark
   shows "Cannot find a dashboard with id ..." until the pak is installed.
2. Administration > Integrations > Repository: install the 2.1.1 pak with
   "Install the PAK file even if it is already installed". There is no need
   to uninstall first, and the adapter account stays.
3. Integrations > Accounts: if the Cluster Performance Risk account is not
   collecting after the upgrade, stop and start its collection.
4. Open the dashboard from Dashboards > All (Recents can point at a deleted
   copy).

**Do not import this dashboard from a file.** On VCF Operations 9.x an
imported copy lost every widget's object types and configurations ("Heatmap
is not configured", lists showing every object), whether the file came from
this repository or from the UI's own export. Install it with the pak.

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
  Band` property. The shipped dashboard does this since 2.1.1; see
  [Migrating to 2.1.1](#migrating-to-211).
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
   installed" (and "Reset Default Content" ticked, where your version of VCF
   Operations has that option).

## Rolling back
Uninstall 2.0.0, install the 1.3.0 pak and recreate the adapter account.
Attributes already written to native objects remain as history but are no
longer updated.
