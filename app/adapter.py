#  Cluster Performance Risk adapter
#  Self-referential: polls VCF Operations' own Suite API for native cluster/host
#  stats, classifies each into the risk-matrix bands, and republishes a composite
#  0-100 risk score + band per cluster and per host.
#
#  This file is intentionally thin -- it's just the four SDK entry points
#  (test/collect/get_endpoints/get_adapter_definition) plus main(). The actual
#  object-type definitions and metric-gathering logic live in cluster.py and
#  host.py; the plumbing they share lives in suite_api.py (generic Suite API
#  calls) and traversal.py (the one shared cluster->host->VM walk).
import sys
from typing import List

import aria.ops.adapter_logging as logging
import cluster
import host
from aria.ops.adapter_instance import AdapterInstance
from aria.ops.definition.adapter_definition import AdapterDefinition
from aria.ops.result import CollectResult
from aria.ops.result import EndpointResult
from aria.ops.result import TestResult
from aria.ops.timer import Timer
from constants_shared import ADAPTER_KIND
from constants_shared import ADAPTER_NAME
from constants_shared import DEFAULT_MONSTER_VM_THRESHOLD_PCT
from constants_shared import PARAM_MONSTER_VM_THRESHOLD_PCT
from constants_shared import RESOURCE_KIND_CLUSTER
from constants_shared import VMWARE_ADAPTER_KIND
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

        # No credential type is defined here. This adapter is self-referential:
        # AdapterInstance.get_suite_api_client() automatically returns an
        # authenticated client for the VCF Operations instance hosting this
        # adapter, with no user-supplied host/username/password needed.

        cluster.define_object_type(definition)
        host.define_object_type(definition)

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
        result = CollectResult()
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
                clusters = fetch_resources(client, RESOURCE_KIND_CLUSTER, VMWARE_ADAPTER_KIND)
                for cluster_id, cluster_name in clusters:
                    metric_values = cluster.gather_metric_values(client, cluster_id)
                    cluster_vm_metrics, host_records = collect_cluster_and_host_metrics(
                        client, cluster_id, monster_vm_threshold_pct
                    )
                    metric_values.update(cluster_vm_metrics)

                    cluster.build_object(result, cluster_id, cluster_name, metric_values)

                    for host_id, host_name, host_metric_values in host_records:
                        host.build_object(
                            result, host_id, host_name, cluster_name, host_metric_values
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
