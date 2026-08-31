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
from ewccli.commands.commons_infra import get_deployed_server_info
from ewccli.commands.commons_infra import resolve_image_and_flavor
from ewccli.commands.commons_infra import normalize_os_image
from ewccli.commands.commons_infra import pre_deploy_server_setup
from ewccli.commands.commons_infra import identify_server_reconfiguration
from ewccli.commands.commons_infra import deploy_server
from ewccli.commands.commons_infra import post_deploy_server_setup
from ewccli.commands.commons_infra import check_server_conflict_with_inputs




# --- Fake OpenstackBackend for testing -------------------------------------
class FakeImage:
    def __init__(self, name: str):
        self.name = name
        self.created_at = datetime.utcnow()

# --- Mock backend completely -------------------------------------------------
class FakeOpenstackBackend:
    def __init__(self, *args, **kwargs):
        pass  # skip real OpenStack connection

    def find_latest_image(self, conn, prefix: str, federee: str, region: str):
        """
        Fake backend implementation that simulates the real find_latest_image()
        but without calling OpenStack.
        """

        class FakeImage:
            def __init__(self, name):
                self.name = name
                self.created_at = "20250202020202"

        # -------------------------
        # CPU short names
        # -------------------------
        if prefix.startswith("Ubuntu-22.04"):
            return FakeImage("Ubuntu-22.04-20250202020202")

        if prefix.startswith("Ubuntu-24.04"):
            return FakeImage("Ubuntu-24.04-20250202020202")

        if prefix.startswith("Rocky-9"):
            return FakeImage("Rocky-9-20250202020202")

        if prefix.startswith("Rocky-8"):
            return FakeImage("Rocky-8-20250202020202")

        # -------------------------
        # GPU short names
        # -------------------------
        if prefix.startswith("Rocky-9-GGPU") or prefix.startswith("Rocky-9-GPU"):
            return FakeImage("Rocky-9.6-GPU-20250202020202")

        if prefix.startswith("Ubuntu-22.04-GPU"):
            return FakeImage("Ubuntu 22.04 NVIDIA_AI")

        if prefix.startswith("Ubuntu-24.04-GPU"):
            return FakeImage("Ubuntu 24.04 NV_GRID_Open")

        # -------------------------
        # GPU long names (OpenStack)
        # -------------------------
        if prefix == "Ubuntu 22.04 NVIDIA_AI":
            return FakeImage("Ubuntu 22.04 NVIDIA_AI")

        if prefix == "Ubuntu 24.04 NV_GRID_Open":
            return FakeImage("Ubuntu 24.04 NV_GRID_Open")

        if prefix == "Rocky-9.6-GPU":
            return FakeImage("Rocky-9.6-GPU-20250202020202")

        # -------------------------
        # No match
        # -------------------------
        return None

# --- Fixtures ---------------------------------------------------------------
@pytest.fixture
def backend():
    return FakeOpenstackBackend()

@pytest.fixture
def conn():
    return MagicMock()  # mock OpenStack connection

# ---------------------------------------------------------------------------
# PARAMETRIC MATRIX FOR ALL FEDEREE + REGION GPU DEFAULTS
# ---------------------------------------------------------------------------

GPU_DEFAULT_MATRIX = [
    # federee, region, short_gpu_name, os_gpu_name, default_gpu_flavour
    ("ECMWF", "CCI1",
     ewc_hub_config.EWC_CLI_GPU_IMAGES_SITE_MAP["ECMWF"]["CCI1"],
     ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["ECMWF"]["CCI1"],
     ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP["ECMWF"]["CCI1"]),

    ("ECMWF", "CCI2",
     ewc_hub_config.EWC_CLI_GPU_IMAGES_SITE_MAP["ECMWF"]["CCI2"],
     ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["ECMWF"]["CCI2"],
     ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP["ECMWF"]["CCI2"]),

    ("EUMETSAT", "WAW3-1",
     ewc_hub_config.EWC_CLI_GPU_IMAGES_SITE_MAP["EUMETSAT"]["WAW3-1"],
     ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["EUMETSAT"]["WAW3-1"],
     ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP["EUMETSAT"]["WAW3-1"]),

    ("EUMETSAT", "ECIS-R1",
     ewc_hub_config.EWC_CLI_GPU_IMAGES_SITE_MAP["EUMETSAT"]["ECIS-R1"],
     ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["EUMETSAT"]["ECIS-R1"],
     ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP["EUMETSAT"]["ECIS-R1"]),

    ("EUMETSAT", "ECIS-R2",
     ewc_hub_config.EWC_CLI_GPU_IMAGES_SITE_MAP["EUMETSAT"]["ECIS-R2"],
     ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["EUMETSAT"]["ECIS-R2"],
     ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP["EUMETSAT"]["ECIS-R2"]),
]


@pytest.mark.parametrize(
    "federee, region, short_gpu, os_gpu, default_flavour",
    GPU_DEFAULT_MATRIX
)
def test_gpu_defaults_all_regions(conn, backend, federee, region, short_gpu, os_gpu, default_flavour):
    with patch("ewccli.commands.commons_infra.normalize_os_image",
               return_value=(os_gpu, True)):
        code, msg, result = resolve_image_and_flavor(
            conn,
            backend,
            federee=federee,
            region=region,
            flavour_name=None,
            image_name=None,
            is_gpu=True,
        )

    assert code == 0
    assert result["normalized_image_name"] == os_gpu
    assert result["flavour_name"] == default_flavour


# ---------------------------------------------------------------------------
# PARAMETRIC MATRIX FOR ALL CPU DEFAULTS
# ---------------------------------------------------------------------------

CPU_DEFAULT_MATRIX = [
    ("ECMWF", "CCI1", ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP["ECMWF"]["CCI1"]),
    ("ECMWF", "CCI2", ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP["ECMWF"]["CCI2"]),
    ("EUMETSAT", "WAW3-1", ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP["EUMETSAT"]["WAW3-1"]),
    ("EUMETSAT", "ECIS-R1", ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP["EUMETSAT"]["ECIS-R1"]),
    ("EUMETSAT", "ECIS-R2", ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP["EUMETSAT"]["ECIS-R2"]),
]


@pytest.mark.parametrize(
    "federee, region, default_flavour",
    CPU_DEFAULT_MATRIX
)
def test_cpu_defaults_all_regions(conn, backend, federee, region, default_flavour):
    with patch("ewccli.commands.commons_infra.normalize_os_image",
               return_value=("Ubuntu-22.04", True)):
        code, msg, result = resolve_image_and_flavor(
            conn,
            backend,
            federee=federee,
            region=region,
            flavour_name=None,
            image_name=None,
            is_gpu=False,
        )

    assert code == 0
    assert result["flavour_name"] == default_flavour


# ---------------------------------------------------------------------------
# GPU FLAVOUR MISMATCH FOR ALL REGIONS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "federee, region",
    [(f, r) for f in ewc_hub_config.GPU_FLAVOURS_MAP for r in ewc_hub_config.GPU_FLAVOURS_MAP[f]]
)
def test_gpu_flavour_mismatch_all_regions(conn, backend, federee, region):
    with patch("ewccli.commands.commons_infra.normalize_os_image",
               return_value=(ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP[federee][region], True)):
        code, msg, result = resolve_image_and_flavor(
            conn,
            backend,
            federee=federee,
            region=region,
            flavour_name=ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP.get(federee, {}).get(region, "cpu-flavour"),
            image_name=None,
            is_gpu=True,
        )

    assert code == 1
    assert "Invalid flavour" in msg


# ---------------------------------------------------------------------------
# GPU IMAGE MISMATCH FOR ALL REGIONS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "federee, region",
    [(f, r) for f in ewc_hub_config.GPU_FLAVOURS_MAP for r in ewc_hub_config.GPU_FLAVOURS_MAP[f]]
)
def test_gpu_image_mismatch_all_regions(conn, backend, federee, region):
    with patch("ewccli.commands.commons_infra.normalize_os_image",
               return_value=("Ubuntu-22.04", False)):  # CPU image
        code, msg, result = resolve_image_and_flavor(
            conn,
            backend,
            federee=federee,
            region=region,
            flavour_name=ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP[federee][region],
            image_name="Ubuntu-22.04",
            is_gpu=True,
        )

    assert code == 1
    assert "Invalid image" in msg


# ---------------------------------------------------------------------------
# GPU IMAGE REQUIRES GPU FLAVOUR FOR ALL REGIONS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "federee, region",
    [(f, r) for f in ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP for r in ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP[f]]
)
def test_gpu_image_requires_gpu_flavour_all_regions(conn, backend, federee, region):
    gpu_os_image = ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP[federee][region]

    with patch("ewccli.commands.commons_infra.normalize_os_image",
               return_value=(gpu_os_image, False)):
        code, msg, result = resolve_image_and_flavor(
            conn,
            backend,
            federee=federee,
            region=region,
            flavour_name=ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP.get(federee, {}).get(region, "cpu-flavour"),
            image_name=gpu_os_image,
            is_gpu=False,
        )

    assert code == 1
    assert "Invalid flavour" in msg


# ---------------------------------------------------------------------------
# CPU SHORT NAMES (exact match)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cpu_image", ewc_hub_config.EWC_CLI_CPU_IMAGES)
def test_normalize_cpu_short_names(cpu_image):
    normalized, is_short = normalize_os_image(
        image_name=cpu_image,
        federee="EUMETSAT",
        region="WAW3-1",
    )
    assert normalized == cpu_image
    assert is_short is True


# ---------------------------------------------------------------------------
# EUMETSAT GPU: exact OS GPU names
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "federee, region, os_gpu",
    [
        ("EUMETSAT", "WAW3-1", ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["EUMETSAT"]["WAW3-1"]),
        ("EUMETSAT", "ECIS-R1", ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["EUMETSAT"]["ECIS-R1"]),
        ("EUMETSAT", "ECIS-R2", ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["EUMETSAT"]["ECIS-R2"]),
    ]
)
def test_normalize_eumetsat_gpu_os_names(federee, region, os_gpu):
    normalized, is_short = normalize_os_image(
        image_name=os_gpu,
        federee=federee,
        region=region,
    )
    assert normalized == os_gpu
    assert is_short is False


# ---------------------------------------------------------------------------
# EUMETSAT GPU: short names → OS GPU names
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "federee, region, short_gpu",
    [
        ("EUMETSAT", "WAW3-1", "Ubuntu-22.04-GPU"),
        ("EUMETSAT", "ECIS-R1", "Ubuntu-24.04-GPU"),
        ("EUMETSAT", "ECIS-R2", "Ubuntu-24.04-GPU"),
    ]
)
def test_normalize_eumetsat_gpu_short_names(federee, region, short_gpu):
    expected = ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP[federee][region]
    normalized, is_short = normalize_os_image(
        image_name=short_gpu,
        federee=federee,
        region=region,
    )
    assert normalized == expected
    assert is_short is True


# ---------------------------------------------------------------------------
# ECMWF GPU: short name → OS GPU name
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "region, short_gpu",
    [
        ("CCI1", "Rocky-9-GPU"),
        ("CCI2", "Rocky-9-GPU"),
    ]
)
def test_normalize_ecmwf_gpu_short_names(region, short_gpu):
    expected = ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["ECMWF"][region]
    normalized, is_short = normalize_os_image(
        image_name=short_gpu,
        federee="ECMWF",
        region=region,
    )
    assert normalized == expected
    assert is_short is True


# ---------------------------------------------------------------------------
# ECMWF GPU: Rocky-9.6-GPU-<timestamp> → Rocky-9.6-GPU
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "region, image_name",
    [
        ("CCI1", "Rocky-9.6-GPU-20251107150148"),
        ("CCI2", "Rocky-9.6-GPU-20251107150148"),
    ]
)
def test_normalize_ecmwf_gpu_timestamp(region, image_name):
    expected = ewc_hub_config.EWC_CLI_OS_GPU_IMAGES_SITE_MAP["ECMWF"][region]
    normalized, is_short = normalize_os_image(
        image_name=image_name,
        federee="ECMWF",
        region=region,
    )
    assert normalized == expected
    # short name only if identical
    assert is_short == (normalized == image_name)


# ---------------------------------------------------------------------------
# Rocky standard normalization: Rocky-9.6-<timestamp> → Rocky-9
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "image_name, expected",
    [
        ("Rocky-9.6-20251107141503", "Rocky-9"),
        ("Rocky-8.3-20240101120000", "Rocky-8"),
    ]
)
def test_normalize_rocky_standard(image_name, expected):
    normalized, is_short = normalize_os_image(
        image_name=image_name,
        federee="ECMWF",
        region="CCI1",
    )
    assert normalized == expected
    assert is_short == (expected == image_name)


# ---------------------------------------------------------------------------
# Ubuntu standard normalization: Ubuntu-24.04-<timestamp> → Ubuntu-24.04
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "image_name, expected",
    [
        ("Ubuntu-24.04-20251107141503", "Ubuntu-24.04"),
        ("Ubuntu-22.04-20240101120000", "Ubuntu-22.04"),
    ]
)
def test_normalize_ubuntu_standard(image_name, expected):
    normalized, is_short = normalize_os_image(
        image_name=image_name,
        federee="EUMETSAT",
        region="WAW3-1",
    )
    assert normalized == expected
    assert is_short == (expected == image_name)


# ---------------------------------------------------------------------------
# Invalid images → None
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "image_name",
    [
        "InvalidOS",
        "SomethingElse",
        "Rocky-XYZ",
        "Ubuntu-XYZ",
        "GPU-Unknown",
        "",
        "   ",
    ]
)
def test_normalize_invalid_images(image_name):
    normalized, is_short = normalize_os_image(
        image_name=image_name,
        federee="EUMETSAT",
        region="WAW3-1",
    )
    assert normalized is None
    assert is_short is False

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


def test_pre_deploy_server_setup_invalid_encoded_keys(conn):
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

    with patch("ewccli.commands.commons_infra.check_ssh_keys_exist"), \
         patch("ewccli.commands.commons_infra.resolve_image_and_flavor",
               return_value=(0, "ok", {
                   "image_name": "Ubuntu-22.04",
                   "normalized_image_name": "Ubuntu-22.04",
                   "flavour_name": "m1.small"
               })), \
         patch("ewccli.commands.commons_infra.save_encoded_ssh_keys",
               return_value=(False, False)):

        code, msg, outputs = pre_deploy_server_setup(
            openstack_backend=backend,
            openstack_api=conn,
            federee="EUMETSAT",
            region="WAW3-1",
            server_inputs=server_inputs,
            ssh_public_key_path="/tmp/id.pub",
            ssh_private_key_path="/tmp/id",
            ssh_private_encoded="AAA",
            ssh_public_encoded="BBB"
        )

    assert code == 1
    assert "Both encoded SSH keys are invalid" in msg


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

    with patch("ewccli.commands.commons_infra.check_ssh_keys_exist"), \
         patch("ewccli.commands.commons_infra.resolve_image_and_flavor",
               return_value=(0, "ok", {
                   "image_name": "Ubuntu-22.04",
                   "normalized_image_name": "Ubuntu-22.04",
                   "flavour_name": "m1.small"
               })):

        code, msg, outputs = pre_deploy_server_setup(
            openstack_backend=backend,
            openstack_api=conn,
            federee="EUMETSAT",
            region="WAW3-1",
            server_inputs=server_inputs,
            ssh_public_key_path="/tmp/id.pub",
            ssh_private_key_path="/tmp/id"
        )

    assert code == 0
    assert "successfully" in msg
    assert outputs["resolved_image_name"] == "Ubuntu-22.04"
    assert outputs["resolved_flavour_name"] == "m1.small"


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

    with patch("ewccli.commands.commons_infra.check_ssh_keys_exist"), \
         patch("ewccli.commands.commons_infra.resolve_image_and_flavor",
               return_value=(0, "ok", {
                   "image_name": "Ubuntu-22.04",
                   "normalized_image_name": "Ubuntu-22.04",
                   "flavour_name": "m1.small"
               })):

        code, msg, outputs = pre_deploy_server_setup(
            openstack_backend=backend,
            openstack_api=conn,
            federee="EUMETSAT",
            region="WAW3-1",
            server_inputs=server_inputs,
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
    assert msg == "[Identify Server Reconfiguration] No reconfiguration needed."
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


def test_check_server_conflict_security_groups_order_insensitive():
    server_info = MagicMock()
    server_info.security_groups = [
        {"name": "http-https-only"},
        {"name": "8080"},
        {"name": "ssh"},
    ]

    diffs = check_server_conflict_with_inputs(
        server_info,
        security_groups=("ssh", "http-https-only", "8080"),
    )

    assert diffs == []


def test_check_server_conflict_security_groups_reports_real_mismatch():
    server_info = MagicMock()
    server_info.security_groups = [
        {"name": "http-https-only"},
        {"name": "8080"},
    ]

    diffs = check_server_conflict_with_inputs(
        server_info,
        security_groups=("ssh", "http-https-only", "8080"),
    )

    assert diffs == [
        (
            "Security Groups",
            "http-https-only,8080",
            "ssh,http-https-only,8080",
        )
    ]


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
        "extra_volume": None
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
        "extra_volume": None
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
            # first call (before refresh)
            (0, "ok", {"internal_ip_machine": "10.0.0.5"}),
            # second call (after refresh)
            (0, "ok", {
                "internal_ip_machine": "10.0.0.5",
                "external_ip_machine": "1.2.3.4"
            }),
        ],
    ):
        server_inputs = {
            "server_name": "vm1",
            "external_ip": False,
        }

        from ewccli.commands.commons_infra import post_deploy_server_setup

        code, msg, outputs = post_deploy_server_setup(
            openstack_backend=backend,
            openstack_api=conn,
            federee="EUMETSAT",
            server_inputs=server_inputs,
            server_info=initial_server_info,
        )

    assert code == 0
    assert outputs["internal_ip_machine"] == "10.0.0.5"
    assert outputs["external_ip_machine"] == "1.2.3.4"


def test_post_deploy_server_setup_missing_ip(conn):
    backend = MagicMock()
    initial_server_info = MagicMock()

    with patch(
        "ewccli.commands.commons_infra.resolve_machine_ip",
        return_value=(0, "ok", None),
    ):
        server_inputs = {
            "server_name": "vm1",
            "internal_ip": "10.0.0.56",
            "external_ip": False,
        }

        code, msg, outputs = post_deploy_server_setup(
            openstack_backend=backend,
            openstack_api=conn,
            federee="EUMETSAT",
            server_inputs=server_inputs,
            server_info=initial_server_info,
        )

    assert code == 1
    assert "No IPs identified" in msg


def test_create_server_command_success(conn):
    backend = MagicMock()

    server_inputs = {
        "server_name": "vm1",
        "keypair_name": "mykey",
        "external_ip": False,
        "networks": ("private",),
        "security_groups": ("ssh",),
    }

    pre_deploy_outputs = {
        "normalized_image_name": "Ubuntu-22.04",
        "networks": ("private",),
        "security_groups": ("ssh",),
    }

    deploy_outputs = {
        "server_info": {"id": "123", "name": "vm1"},
    }

    post_deploy_outputs = {
        "internal_ip_machine": "10.0.0.5",
        "external_ip_machine": "1.2.3.4",
    }

    with patch(
        "ewccli.commands.commons_infra.pre_deploy_server_setup",
        return_value=(0, "ok", pre_deploy_outputs),
    ) as mock_pre, patch(
        "ewccli.commands.commons_infra.identify_server_reconfiguration",
        return_value=(0, "[Identify Server Reconfiguration] No reconfiguration needed.", {})
    ) as mock_identify, patch(
        "ewccli.commands.commons_infra.deploy_server",
        return_value=(0, "ok", deploy_outputs),
    ) as mock_deploy, patch(
        "ewccli.commands.commons_infra.post_deploy_server_setup",
        return_value=(0, "ok", post_deploy_outputs),
    ) as mock_post:

        from ewccli.commands.commons_infra import create_server_command

        code, msg, outputs = create_server_command(
            backend,
            conn,
            "EUMETSAT",
            "WAW3-1",
            server_inputs,
            ssh_public_key_path="/tmp/id.pub",
            ssh_private_key_path="/tmp/id",
        )

    assert code == 0
    assert outputs["normalized_image_name"] == "Ubuntu-22.04"
    assert outputs["internal_ip_machine"] == "10.0.0.5"
    assert outputs["external_ip_machine"] == "1.2.3.4"

    mock_pre.assert_called_once()
    mock_identify.assert_called_once()
    mock_deploy.assert_called_once()
