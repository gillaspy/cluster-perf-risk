# The base-adapter image is built automatically by the integration SDK.
FROM base-adapter:python-1.2.0
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
COPY app app
