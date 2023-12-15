#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from typing import Dict

import yaml
from charms.kubeflow_dashboard.v0.kubeflow_dashboard_links import (
    DashboardLink,
    KubeflowDashboardLinksRequirer,
)
from jinja2 import Template
from ops.charm import CharmBase
from ops.framework import Object
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces

# from .oci_image import OCIImageResource, OCIImageResourceError


def render_template(template_path: str, context: Dict) -> str:
    """
    Render a Jinja2 template.

    This function takes the file path of a Jinja2 template and a context dictionary
    containing the variables for template rendering. It loads the template,
    substitutes the variables in the context, and returns the rendered content.

    Args:
        template_path (str): The file path of the Jinja2 template.
        context (Dict): A dictionary containing the variables for template rendering.

    Returns:
        str: The rendered template content.
    """
    template = Template(Path(template_path).read_text())
    rendered_template = template.render(**context)
    return rendered_template


class CheckFailed(Exception):
    """Raise this exception if one of the checks in main fails."""

    def __init__(self, msg: str, status_type=None):
        super().__init__()

        self.msg = str(msg)
        self.status_type = status_type
        self.status = status_type(self.msg)


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.log = logging.getLogger(__name__)
        self.image = OCIImageResource(self, "oci-image")
        self.log.info("Setting up kimwnasptd...")

        for event in [
            self.on.config_changed,
            self.on.install,
            self.on.upgrade_charm,
            self.on.leader_elected,
            self.on["ingress"].relation_changed,
        ]:
            self.framework.observe(event, self.main)

        self.kubeflow_dashboard_sidebar = KubeflowDashboardLinksRequirer(
            charm=self,
            relation_name="dashboard-links",
            dashboard_links=[
                DashboardLink(
                    text="Volumes",
                    link="/volumes/",
                    type="item",
                    icon="device:storage",
                    location="menu",
                ),
            ],
        )

    def main(self, event):
        try:
            self._check_leader()

            interfaces = self._get_interfaces()

            self.log.info("Getting image details...")
            image_details = self._check_image_details()
            self.log.info("Image details: %s", image_details)

        except CheckFailed as check_failed:
            self.model.unit.status = check_failed.status
            return

        self._configure_mesh(interfaces)

        config = self.model.config

        self.model.unit.status = MaintenanceStatus("Setting pod spec")

        self.model.pod.set_spec(
            {
                "version": 3,
                "serviceAccount": {
                    "roles": [
                        {
                            "global": True,
                            "rules": [
                                {
                                    "apiGroups": [""],
                                    "resources": ["namespaces", "pods"],
                                    "verbs": ["get", "list"],
                                },
                                {
                                    "apiGroups": ["authorization.k8s.io"],
                                    "resources": ["subjectaccessreviews"],
                                    "verbs": ["create"],
                                },
                                {
                                    "apiGroups": [""],
                                    "resources": ["persistentvolumeclaims"],
                                    "verbs": [
                                        "create",
                                        "delete",
                                        "get",
                                        "list",
                                        "watch",
                                        "update",
                                        "patch",
                                    ],
                                },
                                {
                                    "apiGroups": ["storage.k8s.io"],
                                    "resources": ["storageclasses"],
                                    "verbs": ["get", "list", "watch"],
                                },
                                {
                                    "apiGroups": [""],
                                    "resources": ["events"],
                                    "verbs": ["list"],
                                },
                                {
                                    "apiGroups": ["kubeflow.org"],
                                    "resources": ["notebooks"],
                                    "verbs": ["list"],
                                },
                                {
                                    "apiGroups": ["kubeflow.org"],
                                    "resources": ["pvcviewers"],
                                    "verbs": ["get", "list", "create", "delete"],
                                },
                            ],
                        }
                    ]
                },
                "containers": [
                    {
                        "name": "volumes-web-app",
                        "imageDetails": image_details,
                        "envConfig": {
                            "USERID_HEADER": "kubeflow-userid",
                            "USERID_PREFIX": "",
                            "APP_SECURE_COOKIES": str(config["secure-cookies"]).lower(),
                            "BACKEND_MODE": config["backend-mode"],
                            "APP_PREFIX": "/volumes",
                            "VOLUME_VIEWER_IMAGE": config["volume-viewer-image"],
                        },
                        "ports": [{"name": "http", "containerPort": config["port"]}],
                        "volumeConfig": [
                            {
                                "name": "viewer-spec",
                                "mountPath": "/etc/config/",  # xwris to .yaml?
                                "files": [
                                    {
                                        "path": "viewer-spec.yaml",
                                        "content": render_template(
                                            "src/templates/viewer-spec.yaml.j2", {}
                                        ),
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
            k8s_resources={
                "configMaps": {
                    "volumes-web-app-viewer-spec-ck6bhh4bdm": {
                        "viewer-spec.yaml": render_template(
                            "src/templates/viewer-spec.yaml.j2", {}
                        ),
                    },
                },
            },
        )

        self.model.unit.status = ActiveStatus()

    def _configure_mesh(self, interfaces):
        if interfaces["ingress"]:
            interfaces["ingress"].send_data(
                {
                    "prefix": "/volumes",
                    "rewrite": "/",
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                }
            )

    def _check_leader(self):
        if not self.unit.is_leader():
            # We can't do anything useful when not the leader, so do nothing.
            raise CheckFailed("Waiting for leadership", WaitingStatus)

    def _get_interfaces(self):
        try:
            interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            raise CheckFailed(err, WaitingStatus)
        except NoCompatibleVersions as err:
            raise CheckFailed(err, BlockedStatus)
        return interfaces

    def _check_image_details(self):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            raise CheckFailed(f"{e.status.message}", e.status_type)
        return image_details


# Helper
class OCIImageResource(Object):
    def __init__(self, charm, resource_name):
        super().__init__(charm, resource_name)
        self.resource_name = resource_name
        self.log = logging.getLogger(__name__)

    def fetch(self) -> Dict:
        try:
            self.log.info("Trying to fetch resource_path")
            resource_path = self.model.resources.fetch(self.resource_name)
        except ModelError as e:
            self.log.error(e)
            raise MissingResourceError(self.resource_name) from e
        if not resource_path.exists():
            self.log.error("Resource path doesn't exist")
            raise MissingResourceError(self.resource_name)
        resource_text = Path(resource_path).read_text()
        if not resource_text:
            self.log.error("Resource text doesn't exist.")
            raise MissingResourceError(self.resource_name)
        try:
            resource_data = yaml.safe_load(resource_text)
        except yaml.YAMLError as e:
            raise InvalidResourceError(self.resource_name) from e
        else:
            # Translate the data from the format used by the charm store to the
            # format used by the Juju K8s pod spec, since that is how this is
            # typically used:
            # {
            #   'imagePath': image,
            #   'password': pwd,
            #   'username': user
            # }
            # where imagePath is the only mandatory field.
            image_info = {}
            try:
                image_info["imagePath"] = resource_data["registrypath"]
            except KeyError as e:
                raise InvalidResourceError(self.resource_name) from e

            if "username" in resource_data:
                image_info["username"] = resource_data["username"]
            if "password" in resource_data:
                image_info["password"] = resource_data["password"]
            return image_info


class OCIImageResourceError(ModelError):
    status_type = BlockedStatus
    status_message = "Resource error"

    def __init__(self, resource_name):
        super().__init__(resource_name)
        self.status = self.status_type(
            "{}: {}".format(self.status_message, resource_name)
        )


class MissingResourceError(OCIImageResourceError):
    status_message = "Missing resource"


class InvalidResourceError(OCIImageResourceError):
    status_message = "Invalid resource"


if __name__ == "__main__":
    main(Operator)
