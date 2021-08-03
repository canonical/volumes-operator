## Kubeflow Volumes Operator

## Description

This charm encompasses the Kubernetes Python operator for Kubeflow Volumes (see
[CharmHub](https://charmhub.io/?q=kubeflow-volumes)).

The Kubeflow Volumes operator is a Python script that wraps the latest released
version of Kubeflow Volumes, providing lifecycle management and handling events
such as install, upgrade, integrate, and remove.

## Usage

Deploy this charm with:

    juju deploy kubeflow-volumes

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

Testing is done via tox:

    tox
