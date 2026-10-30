Cluster Performance Risk — a VCF Operations management pack that adds composite performance-risk scoring to the native vSphere cluster and host objects.

Since 2.0.0 the pack defines no objects of its own: it writes `Performance Risk|<Group>|<Label>` attributes onto the existing `ClusterComputeResource` and `HostSystem` objects. See [Where to find the metrics](#where-to-find-the-metrics) and [docs/METRICS.md](docs/METRICS.md) for metrics and formulas, and [MIGRATION.md](MIGRATION.md) when upgrading from 1.x.

## Where to find the metrics

The pack writes its values onto the native vSphere objects, so they don't appear
in the pack's own metric list on the Repository page. Find them here:

- **On an object:** open a cluster or host, then Metrics (or Properties) >
  **Performance Risk**.
- **In dashboards, views, super metrics and alerts:** pick Cluster Compute
  Resource or Host System, then the `Performance Risk` group. They are listed
  once the first collection has written them.
- **Shipped dashboard:** "Cluster Performance Risk": a scoreboard of every
  cluster's band, the cluster list, and the selected cluster's hosts. It is
  installed with the pak; don't import it from a file (see
  [MIGRATION.md](MIGRATION.md#migrating-to-211)).

Each metric below is a `Performance Risk|<Group>|<Label>` metric with a matching
`Performance Risk|<Group>|<Label> Band` property (green, yellow, orange, red,
or unknown when there is no data).
Both objects also get `Performance Risk|Composite|Risk Score` (0-100),
`Performance Risk|Composite|Risk Band` (the worst band among the metrics),
`Performance Risk|Composite|Risk Band Level` (that band as 0 green to 3 red,
for coloring widgets) and `Performance Risk|Composite|Metrics In Worst Band`.

| Group | Cluster (`ClusterComputeResource`) | Host (`HostSystem`) |
|---|---|---|
| CPU | Max Host Thread Utilization Pct, Overcommit Ratio, Monster VM Size Ratio | Thread Utilization Pct, Reservation Pct, Overcommit Ratio, Monster VM Size Ratio |
| Memory | Max Host Ballooned Pct, Overcommit Ratio, Monster VM Size Ratio, Host Zip Swap Pct | Consumed Pct, Ballooned Pct, Reservation Pct, Overcommit Ratio, Monster VM Size Ratio, Host Zip Swap Pct |
| Storage | Worst Disk Latency Ms, P90 Disk Latency Ms, Max Host Disk IOPS | Worst Disk Latency Ms, P90 Disk Latency Ms |
| Network | Host Dropped Packets Pct, Max Host Throughput Pct | Host Dropped Packets Pct |
| Contention | Worst / P90 vCPU Ready Pct, Worst / P90 vCPU Co-Stop Pct, Worst / P90 VM Memory Contention Pct, Host Memory Contention Pct | Same as cluster, from this host's own VMs |
| Balance | Host CPU Imbalance Ratio, DRS CPU Imbalance, vMotion Pct | Host CPU Imbalance Ratio |

Formulas, thresholds and the composite score are in
[docs/METRICS.md](docs/METRICS.md).

## When collection fails

Since 2.0.4 a failed collection is visible on the adapter instance instead of
looking like a healthy one with no data:

- **Total failure** puts the adapter instance in an error state, with the
  reason: the resource inventory query failed, every cluster failed, or every
  stats call failed (for example, the token was rejected). Nothing is written
  that cycle.
- **Partial failure** (some clusters, or some Suite API calls) is logged as a
  warning listing what failed. Everything that did collect is still written; a
  value whose call failed has no data that cycle, never a guess.
- Every cycle logs, at INFO, `Suite API: <n> calls, <f> failed, <s> stale, <t>s`.

## License

Copyright 2026 Tom Gillaspy. Licensed under the [Apache License, Version 2.0](LICENSE); see `NOTICE`.

## Build and release

GitHub Actions builds the pack (`.github/workflows/build-and-publish.yml`).
Pull requests and pushes to `main` build the adapter image, run `tests/`
inside it, scan it with Trivy and boot it. Nothing is published.

To release, merge to `main`, then:

```
git tag v1.3.1 && git push origin v1.3.1
```

The tag sets the version. The workflow writes it into `manifest.txt` on the
runner before `mp-build`, so there is nothing to bump before tagging; the
stamped file is never committed. The committed `manifest.txt` stays at the
last released version, which is what a hand-run `mp-build` uses.

The workflow runs `mp-build` against `ghcr.io/gillaspy/cluster-perf-risk`,
scans the pushed image, signs the image and the pak with cosign (keyless: no
keys or secrets to manage), attests both with GitHub build provenance, attests
an SBOM for the image, tags the image `1.3.1`, and creates a GitHub Release
with the pak, its signature bundle (`.pak.sigstore.json`) and `SHA256SUMS`.
A `v1.3.1-rc.1` tag publishes
a prerelease and may come from any branch. Its pak carries version `1.3.1`
(`cluster-perf-risk-1.3.1.pak`; a hand-run `mp-build` still writes `ClusterPerfRisk_<version>.pak`); the Release is named `v1.3.1-rc.1` and the image is
tagged `1.3.1-rc.1`.
A version that already exists in GHCR is refused; release a new patch version
instead. `config.json` still points local `mp-build` runs at Docker Hub; the
workflow does not use it.

One-time setup: if the first release stops at the anonymous pull check, the
new GHCR package was created private. Make it public (package settings,
Change visibility) and re-run the failed jobs. If the package already exists
because it was pushed by hand, give this repository Write under the package's
Manage Actions access.

`.trivyignore.yaml` lists the scan findings this repository cannot fix: pip's
own vendored copies of `urllib3` and `msgpack`, and `setuptools` as it appears
in pip's own build-time SBOM, none of which the adapter installs or imports.
Each entry expires, and the scan fails again until it is reviewed. See
[SECURITY.md](SECURITY.md) for how the image is signed and scanned.

### Verifying what you install

VCF Operations checks none of this. The pak names an image digest in GHCR.
Per the VMware SDK documentation, the Cloud Proxy pulls this digest on first
collection, straight from GHCR, with no signature, attestation or
vulnerability check. Verify that digest yourself:

1. Read what the pak points at (`REGISTRY`, `REPOSITORY`, `DIGEST`):

   ```
   unzip -p cluster-perf-risk-1.3.0.pak adapter.zip > adapter.zip
   unzip -p adapter.zip ClusterPerfRisk.conf
   ```

2. Verify that digest and the pak:

   ```
   IMAGE=ghcr.io/gillaspy/cluster-perf-risk@sha256:<DIGEST from step 1>
   ID='^https://github\.com/gillaspy/cluster-perf-risk/\.github/workflows/build-and-publish\.yml@refs/tags/v'
   ISSUER=https://token.actions.githubusercontent.com
   cosign verify "$IMAGE" --certificate-identity-regexp "$ID" --certificate-oidc-issuer "$ISSUER"
   cosign verify-blob cluster-perf-risk-1.3.0.pak --bundle cluster-perf-risk-1.3.0.pak.sigstore.json \
     --certificate-identity-regexp "$ID" --certificate-oidc-issuer "$ISSUER"
   gh attestation verify "oci://$IMAGE" --repo gillaspy/cluster-perf-risk
   gh attestation verify cluster-perf-risk-1.3.0.pak --repo gillaspy/cluster-perf-risk
   trivy image --severity HIGH,CRITICAL --ignore-unfixed "$IMAGE"
   ```

   Trivy shows the `.trivyignore.yaml` findings unless you pass
   `--ignorefile .trivyignore.yaml` from a checkout of the release tag.

3. Private registry or air-gapped site: verify on a connected host as in
   step 2, copy the image keeping its digest, check the mirror serves that
   digest, then point the pak at the mirror without changing `DIGEST`:

   ```
   MIRROR=registry.example.internal/mirror/cluster-perf-risk
   crane copy "$IMAGE" "$MIRROR:1.3.0"
   crane digest "$MIRROR:1.3.0"        # must equal DIGEST from step 1
   cp cluster-perf-risk-1.3.0.pak cluster-perf-risk-1.3.0-mirror.pak
   unzip -o -q cluster-perf-risk-1.3.0-mirror.pak adapter.zip
   unzip -o -q adapter.zip ClusterPerfRisk.conf
   sed -i -e 's|^REGISTRY=.*|REGISTRY=registry.example.internal|' \
          -e 's|^REPOSITORY=.*|REPOSITORY=/mirror/cluster-perf-risk|' ClusterPerfRisk.conf
   zip -q adapter.zip ClusterPerfRisk.conf && zip -q cluster-perf-risk-1.3.0-mirror.pak adapter.zip
   trivy image --severity HIGH,CRITICAL --ignore-unfixed "$MIRROR@sha256:<DIGEST>"
   ```

   `oras copy -r` in place of `crane copy` also carries the signature and
   attestation, so the cosign check can be repeated against the mirror. The
   Cloud Proxy needs anonymous pull from the mirror. Rebuilding with
   `mp-build -r <mirror>` also names the mirror, but it builds and pushes a
   new image with a new digest that this repository never signed, attested or
   scanned, so the checks above no longer apply to it.
