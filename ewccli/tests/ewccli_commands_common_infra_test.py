#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025, 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC commands common methods."""

from unittest.mock import MagicMock
from unittest.mock import patch
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
from ewccli.commands.commons_infra import pre_deploy_server_setup
from ewccli.commands.commons_infra import identify_server_reconfiguration
from ewccli.commands.commons_infra import deploy_server
from ewccli.commands.commons_infra import post_deploy_server_setup




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


def test_pre_deploy_server_setup_success(conn):
    backend = MagicMock()
    backend.check_server_inputs.return_value = (True, "")
    backend.create_keypair.return_value = ((True,), "keypair created")

    server_inputs = {
        "keypair_name": "mykey",
        "is_gpu": False,
        "image_name": None,
        "flavour_name": None,
        "security_groups": (),
        "item_default_security_groups": (),
        "networks": ("private",),
    }

    with patch("ewccli.commands.commons_infra.save_ssh_keys"), \
         patch("ewccli.commands.commons_infra.check_ssh_keys_exist"), \
         patch("ewccli.commands.commons_infra.resolve_image_and_flavor",
               return_value=(0, "ok", {
                   "image_name": "Ubuntu-22.04",
                   "normalized_image_name": "Ubuntu-22.04",
                   "flavour_name": "m1.small"
               })):

        code, msg, outputs = pre_deploy_server_setup(
            backend, conn, "EUMETSAT", server_inputs,
            ssh_public_key_path="/tmp/id.pub",
            ssh_private_key_path="/tmp/id",
            ssh_private_encoded="AAA",
            ssh_public_encoded="BBB"
        )

    assert code == 0
    assert "successfully" in msg


def test_pre_deploy_server_setup_invalid_inputs(conn):
    backend = MagicMock()
    backend.check_server_inputs.return_value = (False, "invalid flavour")

    server_inputs = {
        "keypair_name": "mykey",
        "is_gpu": False,
        "image_name": None,
        "flavour_name": None,
        "security_groups": (),
        "item_default_security_groups": (),
        "networks": ("private",),
    }

    with patch("ewccli.commands.commons_infra.save_ssh_keys"), \
         patch("ewccli.commands.commons_infra.check_ssh_keys_exist"), \
         patch("ewccli.commands.commons_infra.resolve_image_and_flavor",
               return_value=(0, "ok", {
                   "image_name": "Ubuntu-22.04",
                   "normalized_image_name": "Ubuntu-22.04",
                   "flavour_name": "m1.small"
               })):

        code, msg, outputs = pre_deploy_server_setup(
            backend, conn, "EUMETSAT", server_inputs,
            ssh_public_key_path="/tmp/id.pub",
            ssh_private_key_path="/tmp/id"
        )

    assert code == 1
    assert "not valid" in msg


def test_identify_server_reconfiguration_existing_server(conn):
    server_inputs = {
        "server_name": "vm1",
        "keypair_name": "mykey",
        "flavour_name": "m1.small",
        "networks": ("private",),
        "security_groups": ("ssh",),
    }

    pre_deploy_server_outputs = {
        "resolved_image_name": "Ubuntu-22.04",
        "resolved_flavour_name": "m1.small"
    }

    fake_server = MagicMock()
    fake_server.metadata = {"deployed": "ewccli"}
    fake_server.image = MagicMock(id="img123")

    conn.get_server.return_value = fake_server
    conn.compute.find_image.return_value = MagicMock(name="Ubuntu-22.04")

    with patch(
        "ewccli.commands.commons_infra.check_server_conflict_with_inputs",
        return_value={}
    ):
        code, msg, outputs = identify_server_reconfiguration(
            conn,
            server_inputs,
            pre_deploy_server_outputs
        )

    assert code == 0
    assert msg == "No reconfiguration needed"
    assert outputs == {}



def test_identify_server_reconfiguration_wrong_origin(conn):
    server_inputs = {
        "server_name": "vm1",
        "keypair_name": "mykey",
        "flavour_name": "m1.small",
        "networks": ("private",),
        "security_groups": ("ssh",),
    }

    pre_deploy_server_outputs = {
        "resolved_image_name": "Ubuntu-22.04",
        "resolved_flavour_name": "m1.small"
    }

    fake_server = MagicMock()
    fake_server.metadata = {"deployed": "manual"}  # NOT ewccli

    conn.get_server.return_value = fake_server

    code, msg, outputs = identify_server_reconfiguration(
        conn,
        server_inputs,
        pre_deploy_server_outputs
    )

    assert code == 1
    assert "not been deployed with the EWC CLI" in msg
    assert outputs == {}



def test_deploy_server_success(conn):
    backend = MagicMock()

    backend.create_server.return_value = (
        (True,), "server created", {"image": {"id": "img123"}}
    )
    conn.compute.find_image.return_value = MagicMock(name="Ubuntu-22.04")

    server_inputs = {
        "server_name": "vm1",
        "keypair_name": "mykey",
        "networks": ("private",),
        "security_groups": ("ssh",),
        "resolved_image_name": "Ubuntu-22.04",
        "resolved_flavour_name": "m1.small",
    }

    pre_deploy_server_outputs = {
        "resolved_image_name": "Ubuntu-22.04",
        "resolved_flavour_name": "m1.small"
    }

    code, msg, outputs = deploy_server(
        backend, conn, "EUMETSAT", server_inputs, pre_deploy_server_outputs
    )

    assert code == 0
    assert "successfully" in msg
    assert "server_info" in outputs


def test_deploy_server_failure(conn):
    backend = MagicMock()
    backend.create_server.return_value = (
        (False,), "failed to create", None
    )

    server_inputs = {
        "server_name": "vm1",
        "keypair_name": "mykey",
        "networks": ("private",),
        "security_groups": ("ssh",),
        "resolved_image_name": "Ubuntu-22.04",
        "resolved_flavour_name": "m1.small",
    }

    pre_deploy_server_outputs = {
        "resolved_image_name": "Ubuntu-22.04",
        "resolved_flavour_name": "m1.small"
    }

    code, msg, outputs = deploy_server(
        backend, conn, "EUMETSAT", server_inputs, pre_deploy_server_outputs
    )

    assert code == 1
    assert "failed" in msg


def test_post_deploy_server_setup_success(conn):
    backend = MagicMock()

    # initial server_info passed to the function
    initial_server_info = MagicMock()

    # server returned after refresh
    refreshed_server_info = MagicMock()
    conn.get_server.return_value = refreshed_server_info

    with patch(
        "ewccli.commands.commons_infra.resolve_machine_ip",
        side_effect=[
            # first call (before adding IP)
            (0, "ok", {"internal_ip_machine": "10.0.0.5"}),
            # second call (after refresh)
            (0, "ok", {"internal_ip_machine": "10.0.0.5",
                       "external_ip_machine": "1.2.3.4"})
        ]
    ):
        server_inputs = {
            "server_name": "vm1",
            "external_ip": False,
        }

        code, msg, outputs = post_deploy_server_setup(
            backend,
            conn,
            "EUMETSAT",
            server_inputs,
            initial_server_info,   # <-- NEW ARGUMENT
        )

    assert code == 0
    assert outputs["internal_ip_machine"] == "10.0.0.5"
    assert outputs["external_ip_machine"] == "1.2.3.4"


def test_post_deploy_server_setup_missing_ip(conn):
    backend = MagicMock()

    initial_server_info = MagicMock()

    with patch(
        "ewccli.commands.commons_infra.resolve_machine_ip",
        return_value=(0, "ok", None)
    ):
        server_inputs = {
            "server_name": "vm1",
            "external_ip": False,
        }

        code, msg, outputs = post_deploy_server_setup(
            backend,
            conn,
            "EUMETSAT",
            server_inputs,
            initial_server_info,   # <-- NEW ARGUMENT
        )

    assert code == 1
    assert "No IPs identified" in msg


from unittest.mock import MagicMock, patch

def test_create_server_command_success(conn):
    backend = MagicMock()

    server_inputs = {
        "server_name": "vm1",
        "keypair_name": "mykey",
        "external_ip": False,
        "networks": ("private",),
        "security_groups": ("ssh",),
    }

    # --- Mock outputs for each internal step ---
    pre_deploy_outputs = {
        "normalized_image_name": "Ubuntu-22.04",
        "networks": ("private",),
        "security_groups": ("ssh",),
    }

    deploy_outputs = {
        "server_info": {"id": "123", "name": "vm1"}
    }

    post_deploy_outputs = {
        "internal_ip_machine": "10.0.0.5",
        "external_ip_machine": "1.2.3.4",
    }

    with patch("ewccli.commands.commons_infra.pre_deploy_server_setup",
               return_value=(0, "ok", pre_deploy_outputs)) as mock_pre, \
         patch("ewccli.commands.commons_infra.identify_server_reconfiguration") as mock_identify, \
         patch("ewccli.commands.commons_infra.deploy_server",
               return_value=(0, "ok", deploy_outputs)) as mock_deploy, \
         patch("ewccli.commands.commons_infra.post_deploy_server_setup",
               return_value=(0, "ok", post_deploy_outputs)) as mock_post:

        from ewccli.commands.commons_infra import create_server_command

        code, msg, outputs = create_server_command(
            backend,
            conn,
            "EUMETSAT",
            server_inputs,
            ssh_public_key_path="/tmp/id.pub",
            ssh_private_key_path="/tmp/id",
        )

    # --- Assertions ---
    assert code == 0
    assert outputs["normalized_image_name"] == "Ubuntu-22.04"
    assert outputs["internal_ip_machine"] == "10.0.0.5"
    assert outputs["external_ip_machine"] == "1.2.3.4"

    # --- Verify calls ---
    mock_pre.assert_called_once()
    mock_identify.assert_called_once()
    mock_deploy.assert_called_once()
    mock_post.assert_called_once()
