Cluster Performance Risk — a VCF Operations management pack that adds composite performance-risk scoring to the native vSphere cluster and host objects.

Since 2.0.0 the pack defines no objects of its own: it writes `Performance Risk|<Group>|<Label>` attributes onto the existing `ClusterComputeResource` and `HostSystem` objects. See `docs/METRICS.md` for metrics and formulas, and `MIGRATION.md` when upgrading from 1.x.
