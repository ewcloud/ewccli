#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


import pytest
from pathlib import Path
from types import SimpleNamespace

from ewccli.backends.openstack.backend_ostack import OpenstackBackend


@pytest.fixture
def backend():
    """Create OpenstackBackend instance without running __init__."""
    return OpenstackBackend.__new__(OpenstackBackend)


def test_ssh_key_matches_openstack_true(tmp_path, backend):
    """
    Test that matching keys return True.
    """

    key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtestkey user@test"

    pub_file = tmp_path / "id_rsa.pub"
    pub_file.write_text(key)

    keypair = SimpleNamespace(public_key=key)

    result = backend.ssh_key_matches_openstack(
        public_key_path=str(pub_file),
        keypair=keypair,
    )

    assert result is True


def test_ssh_key_matches_openstack_false(tmp_path, backend):
    """
    Test that different keys return False.
    """

    local_key = "ssh-rsa AAAAB3NzaLOCALKEY user@test"
    cloud_key = "ssh-rsa AAAAB3NzaCLOUDKEY user@test"

    pub_file = tmp_path / "id_rsa.pub"
    pub_file.write_text(local_key)

    keypair = SimpleNamespace(public_key=cloud_key)

    result = backend.ssh_key_matches_openstack(
        public_key_path=str(pub_file),
        keypair=keypair,
    )

    assert result is False


def test_ssh_key_matches_openstack_missing_file(tmp_path, backend):
    """
    Test that missing public key file raises ValueError.
    """

    missing_path = tmp_path / "missing.pub"

    keypair = SimpleNamespace(public_key="ssh-rsa AAAATESTKEY")

    with pytest.raises(ValueError):
        backend.ssh_key_matches_openstack(
            public_key_path=str(missing_path),
            keypair=keypair,
        )


def test_ssh_key_comment_ignored(tmp_path, backend):
    """
    Test that comments at the end of the key are ignored.
    """

    local_key = "ssh-rsa AAAATESTKEY local@machine"
    cloud_key = "ssh-rsa AAAATESTKEY cloud@server"

    pub_file = tmp_path / "id_rsa.pub"
    pub_file.write_text(local_key)

    keypair = SimpleNamespace(public_key=cloud_key)

    result = backend.ssh_key_matches_openstack(
        public_key_path=str(pub_file),
        keypair=keypair,
    )

    assert result is True