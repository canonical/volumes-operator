# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

from charm import KubeflowVolumesOperatorCharm
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(KubeflowVolumesOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_valid_config(self):
        self.harness.update_config({"port": 8888})
        assert isinstance(self.harness.charm.unit.status, ActiveStatus)

    def test_invalid_config(self):
        self.harness.update_config({"port": ""})
        assert isinstance(self.harness.charm.unit.status, BlockedStatus)

    def test_manage_workload(self):
        # Check the initial Pebble plan is empty
        initial_plan = self.harness.get_container_pebble_plan("kubeflow-volumes")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "kubeflow-volumes": {
                    "override": "replace",
                    "summary": "kubeflow-volumes",
                    "command": "gunicorn -w 3 --bind 0.0.0.0:5000 "
                    "--access-logfile - entrypoint:app",
                    "startup": "enabled",
                }
            },
        }
        # Get the kubeflow-volumes container from the model
        container = self.harness.model.unit.get_container("kubeflow-volumes")
        # Emit the PebbleReadyEvent carrying the kubeflow-volumes container
        self.harness.charm.on.kubeflow_volumes_pebble_ready.emit(container)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan(
            "kubeflow-volumes"
        ).to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_ingress_relation(self):
        rid = self.harness.add_relation("ingress", "ingress")
        rel = self.harness.model.get_relation("ingress", rid)
        self.harness.add_relation_unit(rid, "ingress/0")
        assert rel.data[self.harness.charm.app] == {
            "service-hostname": "kubeflow-volumes.juju",
            "service-name": "kubeflow-volumes",
            "service-port": 8080,
        }
