This is a VCF Ops Management Pack to add metrics for enhancing cluster capacity monitoring.

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
keys or secrets to manage), attests both with GitHub build provenance, tags
the image `1.3.1`, and creates a GitHub Release with the pak, its signature
bundle (`.pak.sigstore.json`) and `SHA256SUMS`. A `v1.3.1-rc.1` tag publishes
a prerelease and may come from any branch. Its pak carries version `1.3.1`
(`ClusterPerfRisk_1.3.1.pak`); the Release is named `v1.3.1-rc.1` and the image is
tagged `1.3.1-rc.1`.
A version that already exists in GHCR is refused; release a new patch version
instead. `config.json` still points local `mp-build` runs at Docker Hub; the
workflow does not use it.

One-time setup: if the first release stops at the anonymous pull check, the
new GHCR package was created private. Make it public (package settings,
Change visibility) and re-run the failed jobs. If the package already exists
because it was pushed by hand, give this repository Write under the package's
Manage Actions access.

`.trivyignore.yaml` lists the scan findings this repository cannot fix
(`cryptography` pinned by the SDK library, copies vendored inside pip). Each
entry expires, and the scan fails again until it is reviewed.

### Verifying what you install

VCF Operations checks none of this. The pak names an image digest in GHCR.
Per the VMware SDK documentation, the Cloud Proxy pulls this digest on first
collection, straight from GHCR, with no signature, attestation or
vulnerability check. Verify that digest yourself:

1. Read what the pak points at (`REGISTRY`, `REPOSITORY`, `DIGEST`):

   ```
   unzip -p ClusterPerfRisk_1.3.0.pak adapter.zip > adapter.zip
   unzip -p adapter.zip ClusterPerfRisk.conf
   ```

2. Verify that digest and the pak:

   ```
   IMAGE=ghcr.io/gillaspy/cluster-perf-risk@sha256:<DIGEST from step 1>
   ID='^https://github\.com/gillaspy/cluster-perf-risk/\.github/workflows/build-and-publish\.yml@refs/tags/v'
   ISSUER=https://token.actions.githubusercontent.com
   cosign verify "$IMAGE" --certificate-identity-regexp "$ID" --certificate-oidc-issuer "$ISSUER"
   cosign verify-blob ClusterPerfRisk_1.3.0.pak --bundle ClusterPerfRisk_1.3.0.pak.sigstore.json \
     --certificate-identity-regexp "$ID" --certificate-oidc-issuer "$ISSUER"
   gh attestation verify "oci://$IMAGE" --repo gillaspy/cluster-perf-risk
   gh attestation verify ClusterPerfRisk_1.3.0.pak --repo gillaspy/cluster-perf-risk
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
   cp ClusterPerfRisk_1.3.0.pak ClusterPerfRisk_1.3.0-mirror.pak
   unzip -o -q ClusterPerfRisk_1.3.0-mirror.pak adapter.zip
   unzip -o -q adapter.zip ClusterPerfRisk.conf
   sed -i -e 's|^REGISTRY=.*|REGISTRY=registry.example.internal|' \
          -e 's|^REPOSITORY=.*|REPOSITORY=/mirror/cluster-perf-risk|' ClusterPerfRisk.conf
   zip -q adapter.zip ClusterPerfRisk.conf && zip -q ClusterPerfRisk_1.3.0-mirror.pak adapter.zip
   trivy image --severity HIGH,CRITICAL --ignore-unfixed "$MIRROR@sha256:<DIGEST>"
   ```

   `oras copy -r` in place of `crane copy` also carries the signature and
   attestation, so the cosign check can be repeated against the mirror. The
   Cloud Proxy needs anonymous pull from the mirror. Rebuilding with
   `mp-build -r <mirror>` also names the mirror, but it builds and pushes a
   new image with a new digest that this repository never signed, attested or
   scanned, so the checks above no longer apply to it.
