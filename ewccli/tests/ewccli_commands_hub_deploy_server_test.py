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
from unittest.mock import MagicMock
from datetime import datetime, timedelta

from ewccli.tests.ewccli_base_test import ServerInfo
from ewccli.tests.ewccli_base_test import Address
from ewccli.configuration import EWCCLIConfiguration as ewc_hub_config
from ewccli.enums import Federee
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.commands.commons_infra import resolve_machine_ip
from ewccli.commands.commons_infra import normalize_os_image

# ---------------------------------------------------------------------------
# Fake image using Pydantic for strict validation
# ---------------------------------------------------------------------------

class FakeImage(BaseModel):
    name: str
    created_at: datetime


@pytest.fixture
def conn():
    """Mock OpenStack connection with compute.images()."""
    mock_conn = MagicMock()
    mock_conn.compute.images = MagicMock()
    return mock_conn


@pytest.fixture
def finder():
    """Use find_latest_image as unbound method, no backend instance needed."""
    return OpenstackBackend.find_latest_image


# ---------------------------------------------------------------------------
# CPU: Rocky-8
# ---------------------------------------------------------------------------

def test_find_latest_rocky8_cpu(finder, conn, monkeypatch):
    now = datetime.utcnow()
    img_old = FakeImage(name="Rocky-8.9-20250101010101", created_at=now - timedelta(days=10))
    img_new = FakeImage(name="Rocky-8.9-20250202020202", created_at=now)

    conn.compute.images.return_value = [img_old, img_new]

    # Correct target to patch!
    monkeypatch.setattr(
        "ewccli.configuration.EWCCLIConfiguration.EWC_CLI_CPU_IMAGES",
        {"Rocky-8", "Rocky-9", "Ubuntu-22.04", "Ubuntu-24.04"},
    )

    result = finder(None, conn, "Rocky-8")
    assert result == img_new


# ---------------------------------------------------------------------------
# CPU: Ubuntu 22.04
# ---------------------------------------------------------------------------

def test_find_latest_ubuntu_2204_cpu(finder, conn, monkeypatch):
    now = datetime.utcnow()
    img1 = FakeImage(name="Ubuntu-22.04-20250101010101", created_at=now - timedelta(days=5))
    img2 = FakeImage(name="Ubuntu-22.04-20250303030303", created_at=now)

    conn.compute.images.return_value = [img1, img2]

    monkeypatch.setattr(
        "ewccli.configuration.EWCCLIConfiguration.EWC_CLI_CPU_IMAGES",
        {"Rocky-8", "Rocky-9", "Ubuntu-22.04", "Ubuntu-24.04"},
    )

    result = finder(None, conn, "Ubuntu-22.04")
    assert result == img2


# ---------------------------------------------------------------------------
# GPU: Rocky
# ---------------------------------------------------------------------------

def test_find_latest_rocky_gpu(finder, conn, monkeypatch):
    now = datetime.utcnow()
    img1 = FakeImage(name="Rocky-9.6-GPU-20250101010101", created_at=now - timedelta(days=3))
    img2 = FakeImage(name="Rocky-9.6-GPU-20250303030303", created_at=now)

    conn.compute.images.return_value = [img1, img2]

    monkeypatch.setattr(
        "ewccli.configuration.EWCCLIConfiguration.EWC_CLI_CPU_IMAGES",
        {"Rocky-8", "Rocky-9", "Ubuntu-22.04", "Ubuntu-24.04"},
    )

    result = finder(None, conn, "Rocky-9.6-GPU")
    assert result == img2


# ---------------------------------------------------------------------------
# GPU: Ubuntu
# ---------------------------------------------------------------------------

def test_find_latest_ubuntu_gpu(finder, conn, monkeypatch):
    now = datetime.utcnow()
    img1 = FakeImage(name="Ubuntu 22.04 NVIDIA_AI", created_at=now - timedelta(days=1))
    img2 = FakeImage(name="Ubuntu 22.04 NVIDIA_AI", created_at=now)

    conn.compute.images.return_value = [img1, img2]

    # GPU mapping
    monkeypatch.setattr(
        "ewccli.configuration.EWCCLIConfiguration.EWC_CLI_OS_GPU_IMAGES_SITE_MAP",
        {"EUMETSAT": "Ubuntu 22.04 NVIDIA_AI"},
    )

    monkeypatch.setattr(
        "ewccli.configuration.EWCCLIConfiguration.EWC_CLI_CPU_IMAGES",
        {"Rocky-8", "Rocky-9", "Ubuntu-22.04", "Ubuntu-24.04"},
    )

    result = finder(None, conn, "Ubuntu 22.04 NVIDIA_AI")
    assert result == img2


# ---------------------------------------------------------------------------
# No match
# ---------------------------------------------------------------------------

def test_no_matching_images(finder, conn, monkeypatch):
    conn.compute.images.return_value = [
        FakeImage(name="UnrelatedImage", created_at=datetime.utcnow())
    ]

    monkeypatch.setattr(
        "ewccli.configuration.EWCCLIConfiguration.EWC_CLI_CPU_IMAGES",
        {"Rocky-8", "Rocky-9", "Ubuntu-22.04", "Ubuntu-24.04"},
    )

    assert finder(None, conn, "Rocky-8") is None


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
                        Address(
                            addr="192.168.1.100", **{"OS-EXT-IPS:type": "floating"}
                        ),
                    ]
                },
                security_groups=[],
            ),
            0,
            IPResult(
                internal_ip_machine="10.0.0.5", external_ip_machine="192.168.1.100"
            ),
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
                    "private-1": [
                        Address(addr="10.1.1.5"),
                        Address(addr="136.10.10.10"),
                    ],
                    "external-net": [Address(addr="200.100.50.1")],
                },
                security_groups=[],
            ),
            0,
            IPResult(
                internal_ip_machine="10.1.1.5", external_ip_machine="136.10.10.10"
            ),
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
            IPResult(
                internal_ip_machine="10.1.1.5", external_ip_machine="200.100.50.1"
            ),
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


# ======================================================================
# Tests
# ======================================================================

@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    monkeypatch.setattr(
        ewc_hub_config,
        "EWC_CLI_CPU_IMAGES",
        set()
    )
    monkeypatch.setattr(
        ewc_hub_config,
        "EWC_CLI_OS_GPU_IMAGES_SITE_MAP",
        {
            "ECMWF": "Rocky-9.6-GPU",
            "EUMETSAT": "Ubuntu-22.04-NVIDIA_AI",
        }
    )


# ----------------------- CPU Tests -----------------------

def test_exact_cpu_match(monkeypatch):
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_CPU_IMAGES", {"Rocky-8", "Ubuntu-22.04"})

    normalized, exact = normalize_os_image("Rocky-8", "ECMWF")
    assert normalized == "Rocky-8"
    assert exact is True


def test_normalize_rocky_timestamp(monkeypatch):
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_CPU_IMAGES", {"Rocky-9"})

    normalized, exact = normalize_os_image("Rocky-9.6-20251107141503", "ECMWF")
    assert normalized == "Rocky-9"
    assert exact is False


def test_normalize_ubuntu_timestamp(monkeypatch):
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_CPU_IMAGES", {"Ubuntu-24.04"})

    normalized, exact = normalize_os_image("Ubuntu-24.04-20251107141503", "EUMETSAT")
    assert normalized == "Ubuntu-24.04"
    assert exact is False


# ----------------------- EUMETSAT GPU -----------------------

def test_eumetsat_exact_gpu(monkeypatch):
    monkeypatch.setattr(
        ewc_hub_config,
        "EWC_CLI_OS_GPU_IMAGES_SITE_MAP",
        {"EUMETSAT": "Ubuntu-22.04-NVIDIA_AI"}
    )

    normalized, exact = normalize_os_image("Ubuntu-22.04-NVIDIA_AI", "EUMETSAT")
    assert normalized == "Ubuntu-22.04-NVIDIA_AI"
    assert exact is False


def test_eumetsat_translate_generic_gpu(monkeypatch):
    monkeypatch.setattr(
        ewc_hub_config,
        "EWC_CLI_OS_GPU_IMAGES_SITE_MAP",
        {"EUMETSAT": "Ubuntu-22.04-NVIDIA_AI"}
    )

    normalized, exact = normalize_os_image("Ubuntu-22.04-GPU", "EUMETSAT")
    assert normalized == "Ubuntu-22.04-NVIDIA_AI"
    assert exact is True


# ----------------------- ECMWF GPU -----------------------

def test_ecmwf_exact_gpu(monkeypatch):
    monkeypatch.setattr(
        ewc_hub_config,
        "EWC_CLI_OS_GPU_IMAGES_SITE_MAP",
        {"ECMWF": "Rocky-9-GPU"}
    )

    normalized, exact = normalize_os_image("Rocky-9-GPU", "ECMWF")
    assert normalized == "Rocky-9-GPU"
    assert exact is True


def test_ecmwf_timestamp_gpu(monkeypatch):
    monkeypatch.setattr(
        ewc_hub_config,
        "EWC_CLI_OS_GPU_IMAGES_SITE_MAP",
        {"ECMWF": "Rocky-9-GPU"}
    )

    normalized, exact = normalize_os_image("Rocky-9.6-GPU-20250101010101", "ECMWF")
    assert normalized == "Rocky-9-GPU"
    assert exact is False


# ----------------------- Unknown -----------------------

def test_unknown_image(monkeypatch):
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_CPU_IMAGES", {"Rocky-8"})

    normalized, exact = normalize_os_image("NotAnImage", "EUMETSAT")
    assert normalized is None
    assert exact is False

