#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import ANY

from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.backends.openstack.backend_ostack import ExtraVolumesResult


@pytest.fixture
def backend():
    """Create OpenstackBackend instance without running __init__."""
    return OpenstackBackend.__new__(OpenstackBackend)


@pytest.fixture
def fake_conn():
    """Mocked OpenStack connection."""
    conn = SimpleNamespace()
    conn.block_storage = MagicMock()
    return conn


def make_volume(name="vol1", status="available", metadata=None):
    return SimpleNamespace(
        name=name,
        status=status,
        metadata=metadata or {},
    )

def test_list_volumes_default_metadata(backend, fake_conn):
    vol1 = make_volume("v1", metadata={"ewccli": "true"})
    vol2 = make_volume("v2", metadata={"ewccli": "false"})

    fake_conn.block_storage.volumes.return_value = [vol1]

    result = backend.list_volumes(fake_conn)

    fake_conn.block_storage.volumes.assert_called_once_with(
        details=True,
        metadata={"ewccli": "true"},
    )

    assert result == [vol1]


def test_create_volumes_dry_run(backend, fake_conn):
    res, vols, msg = backend.create_volumes(
        conn=fake_conn,
        base_name="server1",
        volume_sizes=(10, 20),
        dry_run=True,
    )

    assert isinstance(res, ExtraVolumesResult)
    assert res.success is True
    assert res.changed is False
    assert vols == []
    assert "Dry Run" in msg



def test_create_volumes_success(backend, fake_conn):
    # Mock create_volume → returns fake volume objects
    created = [
        make_volume("vol1", status="creating"),
        make_volume("vol2", status="creating"),
    ]
    fake_conn.block_storage.create_volume.side_effect = created

    # Mock wait_for_status → returns ready volumes
    ready = [
        make_volume("vol1", status="available"),
        make_volume("vol2", status="available"),
    ]
    fake_conn.block_storage.wait_for_status.side_effect = ready

    res, vols, msg = backend.create_volumes(
        conn=fake_conn,
        base_name="server1",
        volume_sizes=(10, 20),
        metadata={"custom": "yes"},
    )

    assert res.success is True
    assert res.changed is True
    assert len(vols) == 2
    assert vols[0].status == "available"
    assert "Successfully created" in msg

    # Metadata merged correctly
    fake_conn.block_storage.create_volume.assert_any_call(
        size=10,
        name=ANY,
        volume_type=None,
        metadata={
            "ewccli": "true",
            "server_name": "server1",
            "custom": "yes",
        },
    )


def test_delete_volumes_dry_run(backend, fake_conn):
    vol = make_volume("vol1", metadata={"ewccli": "true"})
    fake_conn.block_storage.volumes.return_value = [vol]

    res, deleted, msg = backend.delete_volumes(
        conn=fake_conn,
        dry_run=True,
    )

    assert res.success is True
    assert res.changed is False
    assert deleted == []
    assert "Dry Run" in msg


def test_delete_volumes_success(backend, fake_conn):
    vol = make_volume("vol1", metadata={"ewccli": "true"})
    fake_conn.block_storage.volumes.return_value = [vol]

    res, deleted, msg = backend.delete_volumes(
        conn=fake_conn,
        base_name="server1",
    )

    fake_conn.block_storage.delete_volume.assert_called_once_with(vol, ignore_missing=True)
    fake_conn.block_storage.wait_for_delete.assert_called_once()

    assert res.success is True
    assert res.changed is True
    assert deleted == [vol]
    assert "Deleted 1 volumes" in msg


def test_delete_volumes_failure(backend, fake_conn):
    vol = make_volume("vol1", metadata={"ewccli": "true"})
    fake_conn.block_storage.volumes.return_value = [vol]

    # First attempt fails, second attempt fails → error recorded
    fake_conn.block_storage.delete_volume.side_effect = Exception("boom")

    res, deleted, msg = backend.delete_volumes(
        conn=fake_conn,
        attempts=2,
        retry_delay_s=0,
    )

    assert res.success is False
    assert res.changed is False
    assert deleted == []
    assert "failed" in msg


#############################################################
#############################################################

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