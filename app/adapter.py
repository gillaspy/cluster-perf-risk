#  Cluster Performance Risk adapter (2.0.0: native-object only)
#  Self-referential: polls VCF Operations' own Suite API for native cluster/host
#  stats, classifies each into the risk-matrix bands, and writes a composite
#  0-100 risk score + band, plus the underlying metrics, as write-only
#  "Performance Risk|<Group>|<Label>" attributes onto the existing VMWARE
#  ClusterComputeResource and HostSystem objects. The pack defines and emits no
#  objects of its own.
#
#  This file is intentionally thin -- it's just the four SDK entry points
#  (test/collect/get_endpoints/get_adapter_definition) plus main(). Scoring lives
#  in cluster.py / host.py, the projection in native_projection.py, and the
#  plumbing they share in suite_api.py (generic Suite API calls) and
#  traversal.py (the one shared cluster->host->VM walk).
import sys
import time
from typing import List

import aria.ops.adapter_logging as logging
import cluster
import host
import native_projection
from aria.ops.adapter_instance import AdapterInstance
from aria.ops.definition.adapter_definition import AdapterDefinition
from aria.ops.result import CollectResult
from aria.ops.result import EndpointResult
from aria.ops.result import RelationshipUpdateModes
from aria.ops.result import TestResult
from aria.ops.timer import Timer
from constants_native import CLUSTER_PROJECTION
from constants_native import HOST_PROJECTION
from constants_shared import ADAPTER_KIND
from constants_shared import ADAPTER_NAME
from constants_shared import DEFAULT_MONSTER_VM_THRESHOLD_PCT
from constants_shared import PARAM_MONSTER_VM_THRESHOLD_PCT
from constants_shared import RESOURCE_KIND_CLUSTER
from constants_shared import RESOURCE_KIND_HOST
from constants_shared import VMWARE_ADAPTER_KIND
from suite_api import fetch_resource_keys
from suite_api import fetch_resources
from traversal import collect_cluster_and_host_metrics

logger = logging.getLogger(__name__)


def get_adapter_definition() -> AdapterDefinition:
    with Timer(logger, "Get Adapter Definition"):
        definition = AdapterDefinition(ADAPTER_KIND, ADAPTER_NAME)

        definition.define_int_parameter(
            "container_memory_limit",
            label="Adapter Memory Limit (MB)",
            description="Sets the maximum amount of memory VCF Operations can "
            "allocate to the container running this adapter instance.",
            required=True,
            advanced=True,
            default=1024,
        )
        definition.define_int_parameter(
            PARAM_MONSTER_VM_THRESHOLD_PCT,
            label="Monster VM Threshold (%)",
            description="A VM counts as a CPU (or memory) monster VM when its "
            "vCPU count (or memory) exceeds this percentage of its host's "
            "total CPU cores (or memory) -- a proxy for VMs that may not fit "
            "in one NUMA node.",
            required=False,
            advanced=True,
            default=DEFAULT_MONSTER_VM_THRESHOLD_PCT,
        )

        # No credential type and no object types are defined here. This adapter
        # is self-referential: AdapterInstance.get_suite_api_client() returns an
        # authenticated client for the VCF Operations instance hosting this
        # adapter, and all output goes onto objects owned by the VMWARE adapter.

        logger.debug(f"Returning adapter definition: {definition.to_json()}")
        return definition


def test(adapter_instance: AdapterInstance) -> TestResult:
    with Timer(logger, "Test"):
        # get_suite_api_client() returns None when called from 'test' -- Suite
        # API calls only work inside 'collect'. There's no external host or
        # credential to validate for a self-referential adapter, so success
        # here just confirms the adapter instance itself was constructed.
        return TestResult()


def collect(adapter_instance: AdapterInstance) -> CollectResult:
    with Timer(logger, "Collection"):
        # target_definition makes the SDK treat every VMWARE object as external
        # (emitted only if it carries content). No relationships are sent: the
        # native cluster->host relationships already exist and are not ours.
        result = CollectResult(target_definition=get_adapter_definition())
        result.update_relationships = RelationshipUpdateModes.NONE
        client = adapter_instance.get_suite_api_client()
        if client is None:
            result.with_error(
                "No Suite API client available. This adapter must run on a "
                "Cloud Proxy with access to its own VCF Operations instance."
            )
            return result

        threshold_str = adapter_instance.get_identifier_value(
            PARAM_MONSTER_VM_THRESHOLD_PCT, str(DEFAULT_MONSTER_VM_THRESHOLD_PCT)
        )
        try:
            monster_vm_threshold_pct = float(threshold_str)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid {PARAM_MONSTER_VM_THRESHOLD_PCT} value {threshold_str!r}, "
                f"falling back to default {DEFAULT_MONSTER_VM_THRESHOLD_PCT}"
            )
            monster_vm_threshold_pct = DEFAULT_MONSTER_VM_THRESHOLD_PCT

        try:
            with client:
                started = time.monotonic()
                clusters = fetch_resources(client, RESOURCE_KIND_CLUSTER, VMWARE_ADAPTER_KIND)
                cluster_keys = fetch_resource_keys(client, RESOURCE_KIND_CLUSTER, VMWARE_ADAPTER_KIND)
                host_keys = fetch_resource_keys(client, RESOURCE_KIND_HOST, VMWARE_ADAPTER_KIND)
                clusters_with_hosts = 0
                clusters_projected = 0
                total_hosts = 0
                hosts_projected = 0
                attributes = 0
                for cluster_id, cluster_name in clusters:
                    # One cluster failing must never lose the others.
                    try:
                        metric_values = cluster.gather_metric_values(client, cluster_id)
                        cluster_vm_metrics, host_records = collect_cluster_and_host_metrics(
                            client, cluster_id, monster_vm_threshold_pct
                        )
                        metric_values.update(cluster_vm_metrics)
                        total_hosts += len(host_records)
                        if host_records:
                            clusters_with_hosts += 1
                        else:
                            logger.warning(
                                f"Cluster {cluster_name!r} ({cluster_id}) returned no host data"
                            )

                        n = native_projection.project(
                            result, cluster_keys.get(cluster_id), metric_values,
                            cluster.score(metric_values), CLUSTER_PROJECTION,
                        )
                        if n:
                            clusters_projected += 1
                            attributes += n
                        else:
                            logger.warning(
                                f"No native ClusterComputeResource match for {cluster_name!r} ({cluster_id})"
                            )

                        for host_id, host_name, host_metric_values in host_records:
                            hn = native_projection.project(
                                result, host_keys.get(host_id), host_metric_values,
                                host.score(host_metric_values), HOST_PROJECTION,
                            )
                            if hn:
                                hosts_projected += 1
                                attributes += hn
                            else:
                                logger.warning(
                                    f"No native HostSystem match for {host_name!r} ({host_id})"
                                )
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Collection failed for cluster {cluster_name!r} ({cluster_id})")
                        logger.exception(e)

                logger.info(
                    f"Collected {len(clusters)} clusters ({clusters_with_hosts} with host data), "
                    f"{total_hosts} hosts in {time.monotonic() - started:.1f}s"
                )
                logger.info(
                    f"Native projection: {clusters_projected}/{len(clusters)} clusters, "
                    f"{hosts_projected}/{total_hosts} hosts, {attributes} attributes"
                )

        except Exception as e:
            logger.error("Unexpected collection error")
            logger.exception(e)
            result.with_error(f"Unexpected collection error: {e!r}")

        logger.debug(f"Returning collection result {result.get_json()}")
        return result


def get_endpoints(adapter_instance: AdapterInstance) -> EndpointResult:
    with Timer(logger, "Get Endpoints"):
        # No external HTTPS endpoints beyond VCF Operations itself, which does
        # not need certificate handling here.
        return EndpointResult()


# Main entry point -- unchanged from the mp-init template
def main(argv: List[str]) -> None:
    logging.setup_logging("adapter.log")
    logging.rotate()
    logger.info(f"Running adapter code with arguments: {argv}")
    if len(argv) != 3:
        logger.error("Arguments must be <method> <inputfile> <ouputfile>")
        sys.exit(1)

    method = argv[0]
    try:
        if method == "test":
            test(AdapterInstance.from_input()).send_results()
        elif method == "endpoint_urls":
            get_endpoints(AdapterInstance.from_input()).send_results()
        elif method == "collect":
            collect(AdapterInstance.from_input()).send_results()
        elif method == "adapter_definition":
            result = get_adapter_definition()
            if type(result) is AdapterDefinition:
                result.send_results()
            else:
                logger.info(
                    "get_adapter_definition method did not return an AdapterDefinition"
                )
                sys.exit(1)
        else:
            logger.error(f"Command {method} not found")
            sys.exit(1)
    finally:
        logger.info(Timer.graph())
        sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
