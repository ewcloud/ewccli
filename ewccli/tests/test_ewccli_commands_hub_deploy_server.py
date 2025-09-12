#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC hub deploy server command methods."""

from typing import Optional

import pytest
from pydantic import BaseModel

from ewccli.tests.test_ewccli_base import ServerInfo
from ewccli.tests.test_ewccli_base import Address
from ewccli.configuration import config as ewc_hub_config
from ewccli.enums import Federee
from ewccli.commands.commons_infra import resolve_image_and_flavor
from ewccli.commands.commons_infra import resolve_machine_ip


# Optional: define a Pydantic model for validation in tests
class DeployRequest(BaseModel):
    """
    Pydantic model for deployment request parameters.

    Attributes:
        federee (str): Target federee (e.g., "EUMETSAT", "ECMWF").
        flavour_name (Optional[str]): Optional flavour name.
        image_name (Optional[str]): Optional OS image name.
        is_gpu (bool): Whether GPU-enabled flavour is required.
    """
    federee: str
    flavour_name: str | None = None
    image_name: str | None = None
    is_gpu: bool = False


@pytest.mark.parametrize(
    "deploy_request,expected_status,expected_image,expected_flavour,expected_user",
    [
        # GPU image, default flavour
        (
            DeployRequest(federee=Federee.ECMWF.value, is_gpu=True),
            0,
            ewc_hub_config.DEFAULT_IMAGES_GPU_MAP[Federee.ECMWF.value],
            ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP[Federee.ECMWF.value],
            ewc_hub_config.EWC_CLI_GPU_IMAGES_USER[Federee.ECMWF.value],
        ),
        # GPU image with invalid flavour
        (
            DeployRequest(federee=Federee.ECMWF.value, flavour_name="invalid-flavour", is_gpu=True),
            1,
            None,
            None,
            None,
        ),
        # CPU image, default flavour for EUMETSAT
        (
            DeployRequest(federee=Federee.EUMETSAT.value, is_gpu=False),
            0,
            ewc_hub_config.EWC_CLI_DEFAULT_IMAGE,  # "Rocky-9.5-20250604142417"
            ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP[Federee.EUMETSAT.value],
            ewc_hub_config.EWC_CLI_IMAGES_USER[ewc_hub_config.EWC_CLI_DEFAULT_IMAGE],
        ),
        # Custom CPU image (must use full image ID)
        (
            DeployRequest(federee=Federee.EUMETSAT.value, image_name=ewc_hub_config.EWC_CLI_IMAGES["ubuntu-22.04"], is_gpu=False),
            0,
            ewc_hub_config.EWC_CLI_IMAGES["ubuntu-22.04"],
            ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP[Federee.EUMETSAT.value],
            ewc_hub_config.EWC_CLI_IMAGES_USER[ewc_hub_config.EWC_CLI_IMAGES["ubuntu-22.04"]],
        ),
        # Unsupported image
        (
            DeployRequest(federee=Federee.EUMETSAT.value, image_name="nonexistent", is_gpu=False),
            1,
            None,
            None,
            None,
        ),
    ],
)
def test_resolve_image_and_flavor(
    deploy_request,
    expected_status,
    expected_image,
    expected_flavour,
    expected_user,
):
    """
    Test the `resolve_image_and_flavor` function with various scenarios.

    Scenarios tested:
        1. GPU image with default flavour
        2. GPU image with invalid flavour
        3. CPU image with default flavour
        4. CPU image with custom image
        5. Unsupported image

    Args:
        deploy_request (DeployRequest): Deployment request parameters.
        expected_status (int): Expected status code (0 for success, 1 for error).
        expected_image (str | None): Expected image name in result.
        expected_flavour (str | None): Expected flavour name in result.
        expected_user (str | None): Expected username in result.

    Assertions:
        - Status code matches expected.
        - On success, result dict contains expected image, flavour, and username.
        - On failure, result is None and error message is non-empty.
    """
    status, message, result = resolve_image_and_flavor(
        federee=deploy_request.federee,
        flavour_name=deploy_request.flavour_name,
        image_name=deploy_request.image_name,
        is_gpu=deploy_request.is_gpu,
    )

    assert status == expected_status
    if expected_status == 0:
        assert result != {}
        if expected_image:
            assert result["image_name"] == expected_image
        if expected_flavour:
            assert result["flavour_name"] == expected_flavour
        if expected_user:
            assert result["username"] == expected_user
        assert message == "Success"
    else:
        assert result == {}
        assert message != ""


# Pydantic models

class IPResult(BaseModel):
    """
    Pydantic model representing the result of resolving a machine's IPs.

    Attributes:
        internal_ip_machine (Optional[str]): The internal/private IP of the machine.
        external_ip_machine (Optional[str]): The external/public IP of the machine.
    """
    internal_ip_machine: Optional[str]
    external_ip_machine: Optional[str]


@pytest.mark.parametrize(
    "federee,server_info,expected_status,expected_result",
    [
        # EUMETSAT with both fixed and floating IPs
        (
            Federee.EUMETSAT.value,
            ServerInfo(
                id="server-001",
                name="eumetsat-server",
                flavor={"name": "small"},
                key_name="key1",
                status="ACTIVE",
                addresses={
                    "private": [
                        Address(addr="10.0.0.5", **{"OS-EXT-IPS:type": "fixed"}),
                        Address(addr="192.168.1.100", **{"OS-EXT-IPS:type": "floating"}),
                    ]
                },
                security_groups=[],
            ),
            0,
            IPResult(internal_ip_machine="10.0.0.5", external_ip_machine="192.168.1.100"),
        ),
        # ECMWF with default private/external IP
        (
            Federee.ECMWF.value,
            ServerInfo(
                id="server-002",
                name="ecmwf-server",
                flavor={"name": "medium"},
                key_name="key2",
                status="ACTIVE",
                addresses={
                    "private-1": [Address(addr="10.1.1.5"), Address(addr="136.10.10.10")],
                    "external-net": [Address(addr="200.100.50.1")],
                },
                security_groups=[],
            ),
            0,
            IPResult(internal_ip_machine="10.1.1.5", external_ip_machine="136.10.10.10"),
        ),
        # ECMWF specifying external network
        (
            Federee.ECMWF.value,
            ServerInfo(
                id="server-003",
                name="ecmwf-server-ext",
                flavor={"name": "medium"},
                key_name="key3",
                status="ACTIVE",
                addresses={
                    "private-1": [Address(addr="10.1.1.5")],
                    "external-internet": [Address(addr="200.100.50.1")],
                },
                security_groups=[],
            ),
            0,
            IPResult(internal_ip_machine="10.1.1.5", external_ip_machine="200.100.50.1"),
        ),
        # Missing addresses (should fail)
        (
            Federee.ECMWF.value,
            ServerInfo(
                id="server-004",
                name="ecmwf-server-missing",
                flavor={"name": "small"},
                key_name="key4",
                status="ACTIVE",
                addresses={},
                security_groups=[],
            ),
            1,
            None,
        ),
    ],
)
def test_resolve_machine_ip(federee, server_info, expected_status, expected_result):
    """
    Test the resolve_machine_ip function for multiple scenarios.

    Args:
        federee (str): The federee (EUMETSAT or ECMWF) for which to resolve IPs.
        server_info (ServerInfo): Server information object with addresses.
        expected_status (int): Expected status code returned by the function (0 for success, 1 for error).
        expected_result (Optional[IPResult]): Expected resolved IPs. None for error cases.

    Asserts:
        - The returned status code matches the expected status.
        - The resolved internal and external IPs match the expected result if provided.
        - The result is None in error cases.
    """
    status, message, result = resolve_machine_ip(
        federee,
        server_info.model_dump(by_alias=True, exclude_none=False),
    )
    assert status == expected_status

    if expected_result is not None:
        ip_result = IPResult(**result)
        assert ip_result == expected_result
    else:
        assert result is None
