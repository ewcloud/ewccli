#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC commands common methods."""

from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel
from datetime import datetime

from ewccli.tests.ewccli_base_test import SecurityGroup
from ewccli.tests.ewccli_base_test import ServerInfo

from ewccli.enums import Federee
from ewccli.configuration import EWCCLIConfiguration as ewc_hub_config
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.commands.commons_infra import get_deployed_server_info
from ewccli.commands.commons_infra import resolve_image_and_flavor
from ewccli.commands.commons_infra import normalize_os_image

# --- Fake OpenstackBackend for testing -------------------------------------
class FakeImage:
    def __init__(self, name: str):
        self.name = name
        self.created_at = datetime.utcnow()

# --- Mock backend completely -------------------------------------------------
class FakeOpenstackBackend:
    def __init__(self, *args, **kwargs):
        pass  # skip real OpenStack connection

    def find_latest_image(self, conn, image_prefix: str):
        # Return a fake "latest image" object
        class FakeImage:
            def __init__(self, name):
                self.name = name

        # simulate the "latest image" based on prefix
        if image_prefix.startswith("Ubuntu-22.04"):
            return FakeImage("Ubuntu-22.04-20250202020202")
        elif image_prefix.startswith("Ubuntu-24.04"):
            return FakeImage("Ubuntu-24.04-20250202020202")
        elif image_prefix.startswith("Rocky-9"):
            return FakeImage("Rocky-9-20250202020202")
        elif image_prefix.startswith("Rocky-8"):
            return FakeImage("Rocky-8-20250202020202")
        elif image_prefix.startswith("Rocky-9-GPU"):
            return FakeImage("Rocky-9.6-GPU-20250202020202")
        elif image_prefix.startswith("Ubuntu 22.04 NVIDIA_AI"):
            return FakeImage("Ubuntu 22.04 NVIDIA_AI")
        else:
            return None

# --- Fixtures ---------------------------------------------------------------
@pytest.fixture
def backend():
    return FakeOpenstackBackend()

@pytest.fixture
def conn():
    return MagicMock()  # mock OpenStack connection

# --- Tests -----------------------------------------------------------------
def test_resolve_cpu_defaults(conn, backend):
    code, msg, result = resolve_image_and_flavor(conn, backend, federee="EUMETSAT", is_gpu=False)
    assert code == 0
    assert result["normalized_image_name"] in ewc_hub_config.EWC_CLI_CPU_IMAGES
    assert result["flavour_name"] == ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP["EUMETSAT"]

def test_resolve_eumetsat_gpu_defaults(conn, backend):
    code, msg, result = resolve_image_and_flavor(conn, backend, federee="EUMETSAT", is_gpu=True)
    assert code == 0
    assert result["normalized_image_name"] == ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["EUMETSAT"]
    assert result["flavour_name"] == ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP["EUMETSAT"]

def test_resolve_ecmwf_gpu_defaults(conn, backend):
    code, msg, result = resolve_image_and_flavor(conn, backend, federee="ECMWF", is_gpu=True)
    assert code == 0
    assert result["normalized_image_name"] == ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["ECMWF"]
    assert result["flavour_name"] == ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP["ECMWF"]

def test_resolve_specific_image(conn, backend):
    code, msg, result = resolve_image_and_flavor(
        conn,
        backend,
        federee="EUMETSAT",
        image_name="Ubuntu-22.04-20250202020202",
        flavour_name="vm.a6000.1"
    )
    assert code == 0

    # normalized image name is short version
    normalized, _ = normalize_os_image("Ubuntu-22.04-20250202020202", "EUMETSAT")
    assert result["normalized_image_name"] == normalized
    assert result["flavour_name"] == "vm.a6000.1"

def test_resolve_unknown_image(conn, backend):
    code, msg, result = resolve_image_and_flavor(
        conn,
        backend,
        federee="EUMETSAT",
        image_name="Unknown-OS-1234"
    )
    assert code == 1
    assert "Unsupported OS image" in msg

#################################################################################################
# --- Tests ---
def test_get_deployed_server_info_eumetsat_private_and_manila():
    """Test EUMETSAT federee with private and manila-network addresses."""
    server = ServerInfo(
        id="02406c28-a84a-4829-bd6b-5562cd6eae8c",
        name="test-vm",
        flavor={"original_name": "m1.small"},
        key_name="my-key",
        status="ACTIVE",
        addresses={
            "private": [{"addr": "10.0.0.5", "OS-EXT-IPS:type": "fixed"}],
            "manila-network": [{"addr": "192.168.1.5"}],
        },
        security_groups=[SecurityGroup(name="ssh")],
    )

    vm_info = get_deployed_server_info(
        Federee.EUMETSAT.value,
        server.model_dump(by_alias=True),
        image_name="ubuntu-20.04",
    )

    assert vm_info["id"] == "02406c28-a84a-4829-bd6b-5562cd6eae8c"
    assert vm_info["flavor"] == "m1.small"
    assert vm_info["networks"]["network-private-fixed"] == "10.0.0.5"
    assert vm_info["networks"]["sfs-manila-network"] == "192.168.1.5"
    assert vm_info["security-groups"] == ["ssh"]
    assert vm_info["image"] == "ubuntu-20.04"


def test_get_deployed_server_info_ecmwf_multiple_networks():
    """Test ECMWF federee with multiple networks."""
    server = ServerInfo(
        id="02406c28-b84a-4829-bd6b-5562cd6eae8c",
        name="ecmwf-vm",
        flavor={"original_name": "m2.medium"},
        key_name="ecmwf-key",
        status="BUILD",
        addresses={
            "net1": [{"addr": "172.16.0.10"}, {"addr": "172.16.0.11"}],
            "net2": [{"addr": "10.10.10.5"}],
        },
        security_groups=[SecurityGroup(name="sec1"), SecurityGroup(name="sec2")],
    )

    vm_info = get_deployed_server_info(Federee.ECMWF.value, server.model_dump())

    assert vm_info["id"] == "02406c28-b84a-4829-bd6b-5562cd6eae8c"
    assert vm_info["flavor"] == "m2.medium"
    assert vm_info["networks"]["network-net1"] == ["172.16.0.10", "172.16.0.11"]
    assert vm_info["networks"]["network-net2"] == ["10.10.10.5"]
    assert set(vm_info["security-groups"]) == {"sec1", "sec2"}


def test_get_deployed_server_info_no_addresses():
    """Test server with no addresses."""
    server = ServerInfo(
        id="02406c28-a84a-4829-bd6b-5562cd6eae8c",
        name="no-address-vm",
        flavor={"original_name": "tiny"},
        key_name="none",
        status="SHUTOFF",
        addresses=None,
        security_groups=[],
    )

    vm_info = get_deployed_server_info(Federee.EUMETSAT.value, server.model_dump())

    assert vm_info["networks"] == {}
    assert vm_info["security-groups"] == []
