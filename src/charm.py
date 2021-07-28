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

from charms.nginx_ingress_integrator.v0.ingress import IngressRequires

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer, ConnectionError

logger = logging.getLogger(__name__)


class KubeflowVolumesOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.kubeflow_volumes_pebble_ready,
                               self._manage_workload)
        self.framework.observe(self.on.config_changed, self._manage_workload)
        self.framework.observe(self.on.upgrade_charm, self._manage_workload)

        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self.external_hostname,
                "service-name": self.app.name,
                "service-port": 8080,
            },
        )

    def _manage_workload(self, event):
        """Manage the workload using the Pebble API."""
        if not self._validate_config():
            return

        self.ingress.update_config({"service-hostname": self.external_hostname})

        try:
            # Get a reference the container attribute on the PebbleReadyEvent
            container = event.workload
            # Add intial Pebble config layer using the Pebble API
            container.add_layer("kubeflow-volumes", self.layer, combine=True)
            # Autostart any services that were defined with startup: enabled
            container.autostart()
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

    @property
    def external_hostname(self):
        """Check if hostname has been configured. If not, generate one."""
        return self.config["external-hostname"] or "{}.juju".format(self.app.name)

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
                                   "--access-logfile - entrypoint:app".format(
                                       self.config["port"]),
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(KubeflowVolumesOperatorCharm)
