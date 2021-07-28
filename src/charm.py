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
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

logger = logging.getLogger(__name__)


class KubeflowVolumesOperatorCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.kubeflow_volumes_pebble_ready,
                               self._on_kubeflow_volumes_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self._external_hostname,
                "service-name": self.app.name,
                "service-port": 8080,
            },
        )

    @property
    def _external_hostname(self):
        """
        Check if hostname has been configured. If not, generate one.
        """
        return self.config["external-hostname"] or "{}.juju".format(self.app.name)

    def _on_kubeflow_volumes_pebble_ready(self, event):
        """Define and start a workload using the Pebble API.

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        if not self.model.config.get("port"):
            self.unit.status = BlockedStatus("Missing 'port' configuration")
            return

        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "kubeflow-volumes layer",
            "description": "pebble config layer for kubeflow-volumes",
            "services": {
                "kubeflow-volumes": {
                    "override": "replace",
                    "summary": "kubeflow-volumes",
                    "command": "gunicorn -w 3 --bind 0.0.0.0:{} "
                               "--access-logfile - entrypoint:app".format(
                                   self.model.config["port"]),
                    "startup": "enabled",
                    "environment": {},
                }
            },
        }
        # Add intial Pebble config layer using the Pebble API
        container.add_layer("kubeflow-volumes", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, _):
        """
        Update the layer with new config.
        """
        if not self.model.config.get("port"):
            self.unit.status = BlockedStatus("Missing 'port' configuration")
            return

        self.ingress.update_config(
            {"service-hostname": self.config["external_hostname"]})


if __name__ == "__main__":
    main(KubeflowVolumesOperatorCharm)
