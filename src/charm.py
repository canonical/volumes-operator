#!/usr/bin/env python3
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer, ConnectionError
from serialized_data_interface import (
    NoCompatibleVersions,
    NoVersionsListed,
    get_interfaces,
)

logger = logging.getLogger(__name__)


class KubeflowVolumesOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)

        # Return quickly if we can't verify interface versions
        try:
            self.interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            self.unit.status = WaitingStatus(str(err))
            return
        except NoCompatibleVersions as err:
            self.unit.status = BlockedStatus(str(err))
            return

        self.framework.observe(
            self.on.kubeflow_volumes_pebble_ready, self._manage_workload
        )
        self.framework.observe(self.on.config_changed, self._manage_workload)
        self.framework.observe(self.on.upgrade_charm, self._manage_workload)
        self.framework.observe(
            self.on["ingress"].relation_changed, self._configure_ingress
        )

    def _manage_workload(self, event):
        """Manage the workload using the Pebble API."""
        if not self._validate_config():
            return

        try:
            # Get a reference the container attribute on the PebbleReadyEvent
            container = event.workload
            # Add intial Pebble config layer using the Pebble API
            container.add_layer("kubeflow-volumes", self.layer, combine=True)
            if container.get_service("kubeflow-volumes").is_running():
                container.stop("kubeflow-volumes")
            container.start("kubeflow-volumes")
            self.unit.status = ActiveStatus()
        except ConnectionError:
            self.unit.status = WaitingStatus("Waiting for Pebble")

    def _validate_config(self):
        """Check that charm config settings are valid.

        If the charm config is not valid, will set the unit status to BlockedStatus
        and return False.
        """
        if not self.config["port"]:
            self.unit.status = BlockedStatus("Missing 'port' configuration")
            return False
        return True

    def _configure_ingress(self, event):
        """Sends data for ingress relation."""
        if self.interfaces["ingress"]:
            self.interfaces["ingress"].send_data(
                {
                    "prefix": "/volumes",
                    "rewrite": "/",
                    "service": self.app.name,
                    "port": self.config["port"],
                }
            )

    @property
    def layer(self):
        """Pebble layer for workload."""
        return Layer(
            {
                "summary": "kubeflow-volumes layer",
                "description": "pebble config layer for kubeflow-volumes",
                "services": {
                    "kubeflow-volumes": {
                        "override": "replace",
                        "summary": "kubeflow-volumes",
                        "command": "gunicorn -w 3 --bind 0.0.0.0:{} "
                        "--access-logfile - entrypoint:app".format(self.config["port"]),
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(KubeflowVolumesOperatorCharm)
