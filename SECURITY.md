# Security Policy

## Supported versions

This is a personal, single-maintainer project. Only the most recently
published release (the latest `vX.Y.Z` tag, image tag and pak on the
[Releases page](https://github.com/gillaspy/cluster-perf-risk/releases)) is
supported. Older releases do not receive backported fixes; upgrade to the
latest release to pick up security fixes.

## Reporting a vulnerability

Please report suspected vulnerabilities privately, not in a public issue or
pull request: email **tom.gillaspy@gmail.com** with a description of the
issue, how to reproduce it, and its impact. You should get an acknowledgement
within a few days. Once a fix is available it will ship in a new release and
be noted in that release's notes; please give a reasonable amount of time to
release a fix before any public disclosure.

This does not apply to vulnerabilities in third-party dependencies
(`cryptography`, `urllib3`, the VMware Aria Operations Integration SDK,
etc.) — report those upstream. `.trivyignore.yaml` documents the dependency
findings this repository is already tracking and cannot fix itself.

## Supply chain: what's signed and scanned

Every release is built, scanned and signed by GitHub Actions
(`.github/workflows/build-and-publish.yml`), not by hand:

- **Scanned.** The adapter image is scanned with [Trivy](https://trivy.dev/)
  for every pull request, push to `main`, and release; the release gate fails
  on any fixable HIGH or CRITICAL finding not documented and expiring in
  `.trivyignore.yaml`.
- **Signed.** The published image and its `.pak` are signed keylessly with
  [cosign](https://github.com/sigstore/cosign) (Sigstore; no private key to
  manage or leak).
- **Attested.** The image carries a [SLSA build provenance
  attestation](https://slsa.dev/) and an SBOM attestation, both pushed to the
  registry alongside it; the pak carries its own build provenance attestation.
- **Non-root.** The container runs as the unprivileged `aria-ops-adapter-user`,
  not root.

VCF Operations itself does not check any of this when it installs a pak or
pulls the image. See "Verifying what you install" in
[README.md](README.md#verifying-what-you-install) for the commands to verify
a release yourself (`cosign verify`, `gh attestation verify`, `trivy image`,
`sha256sum -c`) before you trust it.
