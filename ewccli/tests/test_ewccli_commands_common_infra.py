#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC commands common methods."""


from ewccli.tests.test_ewccli_base import SecurityGroup
from ewccli.tests.test_ewccli_base import ServerInfo

from ewccli.enums import Federee
from ewccli.commands.commons_infra import get_deployed_server_info


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
        security_groups=[SecurityGroup(name="ssh")]
    )

    vm_info = get_deployed_server_info(
        Federee.EUMETSAT.value,
        server.model_dump(by_alias=True),
        image_name="ubuntu-20.04"
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
        security_groups=[SecurityGroup(name="sec1"), SecurityGroup(name="sec2")]
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
        security_groups=[]
    )

    vm_info = get_deployed_server_info(Federee.EUMETSAT.value, server.model_dump())

    assert vm_info["networks"] == {}
    assert vm_info["security-groups"] == []
