import dataclasses
import logging

from charmed_kubeflow_chisme.components.pebble_component import PebbleServiceComponent
from ops.pebble import Layer

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class KubeflowVolumesInputs:
    """Defines the required inputs for KubeflowVolumesPebbleService."""

    APP_SECURE_COOKIES: bool
    BACKEND_MODE: str
    VOLUME_VIEWER_IMAGE: str


class KubeflowVolumesPebbleService(PebbleServiceComponent):
    def get_layer(self) -> Layer:
        """Pebble configuration layer for kubeflow-volumes."""
        try:
            inputs: KubeflowVolumesInputs = self._inputs_getter()
        except Exception as err:
            raise ValueError("Failed to get inputs for Pebble container.") from err

        layer = Layer(
            {
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": "entry point for kubeflow-volumes",
                        "command": "/bin/bash -c 'gunicorn -w 3 --bind 0.0.0.0:5000 --access-logfile - entrypoint:app'",  # noqa: E501
                        "startup": "enabled",
                        "environment": {
                            "USERID_HEADER": "kubeflow-userid",
                            "USERID_PREFIX": "",
                            "APP_SECURE_COOKIES": str(inputs.APP_SECURE_COOKIES).lower(),
                            "BACKEND_MODE": inputs.BACKEND_MODE,
                            "APP_PREFIX": "/volumes",
                            "VOLUME_VIEWER_IMAGE": inputs.VOLUME_VIEWER_IMAGE,
                        },
                    }
                }
            }
        )

        logger.debug("computed layer as:")
        logger.debug(layer.to_dict())

        return layer
