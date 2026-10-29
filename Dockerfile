# The base-adapter image is built automatically by the integration SDK.
FROM base-adapter:python-1.2.0
# Debian security updates the base image does not carry yet (openssl/libssl3
# CVE-2026-84782, fixed in 3.0.22-1~deb12u2). Upgrades only packages that are
# already installed. The base image runs as aria-ops-adapter-user, so this one
# step runs as root and the user is restored right after.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade libssl3 openssl \
    && rm -rf /var/lib/apt/lists/*
USER aria-ops-adapter-user
COPY commands.cfg .
COPY adapter_requirements.txt .
RUN pip3 install -r adapter_requirements.txt --upgrade
# vmware-aria-operations-integration-sdk-lib 1.1.0 pins cryptography==44.0.0
# exactly (4 fixed HIGH CVEs). Nothing of ours imports cryptography; the SDK
# library only uses cryptography.x509 (certificate_info.py) for the stable,
# long-standing x509 parsing API, so overriding the pin to the latest release
# is safe. The version is pinned to the one that was tested; bump it
# deliberately (tests + scan), and revisit if the SDK library re-pins.
RUN pip3 install "cryptography==50.0.2"
# certifi from the SDK's dependencies has GHSA-6q48-6c7w-9gw2 (CRITICAL),
# fixed in 2026.10.18. Pinned to that release, like cryptography above.
RUN pip3 install "certifi==2026.10.18"
COPY app app
