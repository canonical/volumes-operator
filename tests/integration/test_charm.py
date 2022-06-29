# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from random import choices
from string import ascii_lowercase
from subprocess import check_output
from time import sleep

import yaml

from lightkube import Client
from lightkube.models.rbac_v1 import PolicyRule
from lightkube.resources.rbac_authorization_v1 import Role
import pytest
from pytest_operator.plugin import OpsTest
from selenium.common.exceptions import JavascriptException, WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire import webdriver

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    charm_name = METADATA["name"]

    my_charm = await ops_test.build_charm(".")
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]

    await ops_test.model.deploy(my_charm, resources={"oci-image": image_path})

    await ops_test.model.wait_for_idle(
        [charm_name],
        wait_for_active=True,
        raise_on_blocked=True,
        raise_on_error=True,
        timeout=300,
    )


@pytest.mark.abort_on_fail
async def test_relate_dependencies(ops_test: OpsTest):
    await ops_test.model.deploy(
        "istio-pilot",
        channel="1.5/stable",
        config={"default-gateway": "kubeflow-gateway"},
        trust=True,
    )

    await ops_test.model.deploy(
        "istio-gateway",
        application_name="istio-ingressgateway",
        channel="1.5/stable",
        trust=True,
    )

    # Patch istio-gateway Role to grant access to its own configmap (needed for istio charm v1.5)
    await patch_istiogateway_role(ops_test=ops_test)

    await ops_test.model.deploy(
        "kubeflow-dashboard", config={"profile": "kubeflow-user"}
    )
    await ops_test.model.deploy("kubeflow-profiles")

    await ops_test.model.add_relation(
        "istio-pilot:istio-pilot", "istio-ingressgateway:istio-pilot"
    )
    await ops_test.model.add_relation("kubeflow-dashboard", "kubeflow-profiles")
    await ops_test.model.add_relation(
        "istio-pilot:ingress", "kubeflow-dashboard:ingress"
    )

    await ops_test.model.add_relation("istio-pilot", "kubeflow-volumes")
    await ops_test.model.wait_for_idle(
        wait_for_units=True,
        raise_on_blocked=True,
        raise_on_error=True,
        timeout=300,
    )


@pytest.fixture()
def driver(request):
    status = yaml.safe_load(check_output(["juju", "status", "--format=yaml"]))
    endpoint = status["applications"]["istio-ingressgateway"]["address"]
    url = f"http://{endpoint}.nip.io/_/volumes/?ns=kubeflow-user"
    options = Options()
    options.headless = True
    options.log.level = "trace"

    kwargs = {
        "options": options,
        "seleniumwire_options": {"enable_har": True},
    }

    with webdriver.Firefox(**kwargs) as driver:
        wait = WebDriverWait(driver, 180, 1, (JavascriptException, StopIteration))
        for _ in range(60):
            try:
                driver.get(url)
                break
            except WebDriverException:
                sleep(5)
        else:
            driver.get(url)

        yield driver, wait, url

        Path(f"/tmp/selenium-{request.node.name}.har").write_text(driver.har)
        driver.get_screenshot_as_file(f"/tmp/selenium-{request.node.name}.png")


# TODO: Reenable tests - Temporarily disabled.  They work locally, but not in CI
# def test_first_access_to_ui(driver):
#     """Access volumes page once for everything to be initialized correctly"""
#
#     driver, wait, url = driver
#
#     # Click "New Volume" button
#     script = fix_queryselector(["main-page", "iframe-container", "iframe"])
#     script += ".contentWindow.document.body.querySelector('#newResource')"
#     wait.until(lambda x: x.execute_script(script))
#     driver.execute_script(script + ".click()")
#
#
# def test_volume(driver):
#     """Ensures a volume can be created and deleted."""
#
#     driver, wait, url = driver
#
#     volume_name = "ci-test-" + "".join(choices(ascii_lowercase, k=10))
#
#     # Click "New Volume" button
#     script = fix_queryselector(["main-page", "iframe-container", "iframe"])
#     script += ".contentWindow.document.body.querySelector('#newResource')"
#     wait.until(lambda x: x.execute_script(script))
#     driver.execute_script(script + ".click()")
#
#     # Enter volume name
#     script = fix_queryselector(["main-page", "iframe-container", "iframe"])
#     script += (
#         ".contentWindow.document.body.querySelector('input[placeholder=\"Name\"]')"
#     )
#     wait.until(lambda x: x.execute_script(script))
#     driver.execute_script(script + '.value = "%s"' % volume_name)
#     driver.execute_script(script + '.dispatchEvent(new Event("input"))')
#
#     # Click submit on the form. Sleep for 1 second before clicking the submit
#     # button due to animations.
#     script = fix_queryselector(["main-page", "iframe-container", "iframe"])
#     script += ".contentWindow.document.body.querySelector('form')"
#     wait.until(lambda x: x.execute_script(script))
#     driver.execute_script(script + '.dispatchEvent(new Event("ngSubmit"))')
#
#     # doc points at the nested Document hidden in all of the shadowroots
#     # Saving as separate variable to make constructing `Document.evaluate`
#     # query easier, as that requires `contextNode` to be equal to `doc`.
#     doc = fix_queryselector(["main-page", "iframe-container", "iframe"])[7:]
#     doc += ".contentWindow.document"
#
#     # Since upstream doesn't use proper class names or IDs or anything, find the
#     # <tr> containing elements that contain the notebook name and `ready`, signifying
#     # that the notebook is finished booting up. Returns a reference to the containing
#     # <tr> element.
#     chonky_boi = "/".join(
#         [
#             f"//*[contains(text(), '{volume_name}')]",
#             "ancestor::tr",
#             "/*[contains(@class, 'ready')]",
#             "ancestor::tr",
#         ]
#     )
#
#     script = evaluate(doc, chonky_boi)
#     wait.until(lambda x: x.execute_script(script))
#
#     # Delete volumes and wait for it to finalize
#     driver.execute_script(evaluate(doc, "//*[contains(text(), 'delete')]") + ".click()")
#     driver.execute_script(
#         f"{doc}.body.querySelector('.mat-dialog-container .mat-warn').click()"
#     )
#
#     script = evaluate(doc, "//*[contains(text(), '{volume_name}')]")
#     wait.until_not(lambda x: x.execute_script(script))


def evaluate(doc, xpath):
    result_type = "XPathResult.FIRST_ORDERED_NODE_TYPE"
    return f'return {doc}.evaluate("{xpath}", {doc}, null, {result_type}, null).singleNodeValue'


def fix_queryselector(elems):
    """Workaround for web components breaking querySelector."""

    selectors = '").shadowRoot.querySelector("'.join(elems)
    return 'return document.querySelector("' + selectors + '")'


async def patch_istiogateway_role(ops_test: OpsTest):
    """Patch the istio-gateway Role so that it can access it's own configmap.

    This can be removed when we move to the sidecar istio v1.11 charm
    """
    # Wait for object that needs patching to be created
    # We should probably just retry the attempt to patch a few times instead of wait, but this
    # is a temp fix anyway
    sleep(15)

    async with ops_test.fast_forward():
        lightkube_client = Client(
            namespace=ops_test.model_name,
        )

        istio_gateway_role_name = "istio-ingressgateway-operator"

        new_policy_rule = PolicyRule(verbs=["*"], apiGroups=["*"], resources=["*"])
        this_role = lightkube_client.get(
            Role,
            istio_gateway_role_name,
        )
        this_role.rules.append(new_policy_rule)
        lightkube_client.patch(Role, istio_gateway_role_name, this_role)

        sleep(30)
