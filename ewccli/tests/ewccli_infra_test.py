#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC infra command."""

import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock
from types import SimpleNamespace

from ewccli.ewccli import cli
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.commands.infra_command import pre_delete_server


# -----------------------------
# CLI runner
# -----------------------------
@pytest.fixture
def runner():
    return CliRunner()

# -------------------------
# Fixtures
# -------------------------


# @pytest.fixture
# def conn():
#     """Mock OpenStack connection."""
#     mock_conn = MagicMock()
#     mock_conn.compute.images = MagicMock()
#     mock_conn.compute.servers = MagicMock()
#     return mock_conn


# @pytest.fixture
# def backend():
#     return OpenstackBackend()


# class FakeServer(SimpleNamespace):
#     def get(self, key, default=None):
#         return getattr(self, key, default)


# def make_server(**kwargs):
#     return FakeServer(**kwargs)


# # -------------------------
# # Tests
# # -------------------------


# def test_basic_server(conn, backend):
#     server = make_server(
#         id="1",
#         name="group2",
#         status="ACTIVE",
#         metadata={"deployed": "ewccli"},
#         image={"id": "img1"},
#         flavor={"original_name": "vm.a6000.4"},
#         key_name="test-keypair",
#         addresses={
#             "private": [
#                 {"addr": "10.0.0.152", "OS-EXT-IPS:type": "fixed"}
#             ]
#         },
#         security_groups=[{"name": "default"}],
#     )

#     image = make_server(id="img1", name="ubuntu")

#     conn.compute.servers.return_value = [server]
#     conn.compute.images.return_value = [image]

#     result = backend.list_servers(conn, show_all=False, federee="EUMETSAT")

#     assert "1" in result
#     assert result["1"]["name"] == "group2"
#     assert result["1"]["image"] == "ubuntu"
#     assert "private-fixed" in result["1"]["networks"]
#     assert result["1"]["security-groups"] == "default"


# def test_security_groups_none(conn, backend):
#     server = make_server(
#         id="1",
#         name="test",
#         status="ACTIVE",
#         metadata={"deployed": "ewccli"},
#         image=None,
#         key_name="test-keypair",
#         flavor={"original_name": "vm"},
#         addresses={},
#         security_groups=None,
#     )

#     conn.compute.servers.return_value = [server]
#     conn.compute.images.return_value = []

#     result = backend.list_servers(conn, show_all=True)

#     assert result["1"]["security-groups"] == ""


# def test_multiple_networks(conn, backend):
#     server = make_server(
#         id="1",
#         name="group1",
#         status="ACTIVE",
#         metadata={"deployed": "ewccli"},
#         image=None,
#         flavor={"original_name": "vm"},
#         key_name="test-keypair",
#         addresses={
#             "private": [
#                 {"addr": "10.0.0.98", "OS-EXT-IPS:type": "fixed"},
#                 {"addr": "64.225.131.199", "OS-EXT-IPS:type": "floating"},
#             ]
#         },
#         security_groups=[{"name": "default"}],
#     )

#     conn.compute.servers.return_value = [server]
#     conn.compute.images.return_value = []

#     result = backend.list_servers(conn, show_all=True, federee="EUMETSAT")

#     networks = result["1"]["networks"]

#     assert "private-fixed" in networks
#     assert "private-floating" in networks


# def test_filtered_by_metadata(conn, backend):
#     server = make_server(
#         id="1",
#         name="ignored",
#         status="ACTIVE",
#         metadata={},  # no deployed=ewccli
#         image=None,
#         key_name="test-keypair",
#         flavor={"original_name": "vm"},
#         addresses={},
#         security_groups=[],
#     )

#     conn.compute.servers.return_value = [server]
#     conn.compute.images.return_value = []

#     result = backend.list_servers(conn, show_all=False)

#     assert result == {}


# def test_show_all(conn, backend):
#     server = make_server(
#         id="1",
#         name="included",
#         status="ACTIVE",
#         metadata={},
#         image=None,
#         key_name="test-keypair",
#         flavor={"original_name": "vm"},
#         addresses={},
#         security_groups=[],
#     )

#     conn.compute.servers.return_value = [server]
#     conn.compute.images.return_value = []

#     result = backend.list_servers(conn, show_all=True)

#     assert "1" in result


# def test_error_server(conn, backend):
#     server = make_server(
#         id="1",
#         name="broken",
#         status="ERROR",
#         metadata={"deployed": "ewccli"},
#         image=None,
#         key_name="test-keypair",
#         flavor={"original_name": "vm"},
#         addresses={},
#         security_groups=None,
#     )

#     conn.compute.servers.return_value = [server]
#     conn.compute.images.return_value = []

#     result = backend.list_servers(conn, show_all=True)

#     assert result["1"]["status"] == "ERROR"


# class FakeVolume:
#     def __init__(self, vol_id, metadata):
#         self.id = vol_id
#         self.metadata = metadata


# def test_pre_delete_no_volumes():
#     backend = MagicMock()
#     api = MagicMock()

# # Mock remove_external_ip so it doesn't crash if external IP exists
#     backend.remove_external_ip.return_value = (
#         MagicMock(success=True),
#         "external IP detached"
#     )

#     server_info = {
#         "id": "server-123",
#         "attached_volumes": [],
#         "addresses": {
#             "private": [
#                 {"addr": "10.0.0.98", "OS-EXT-IPS:type": "fixed"},
#                 {"addr": "64.225.131.199", "OS-EXT-IPS:type": "floating"},
#             ]
#         },
#         "metadata": {"deployed": "ewccli"},
#     }

#     rc, msg = pre_delete_server(
#         openstack_backend=backend,
#         openstack_api=api,
#         federee="EUMETSAT",
#         server_name="vm1",
#         server_info=server_info,
#         dry_run=False,
#     )

#     assert rc == 0
#     assert "finished successfully" in msg


# def test_pre_delete_non_ewccli_volumes():
#     backend = MagicMock()
#     api = MagicMock()

#     # No external IP detach
#     backend.remove_external_ip.return_value = (MagicMock(success=True), "ok")

#     server_info = {
#         "id": "server-123",
#         "attached_volumes": [{"id": "vol1"}],
#         "addresses": {
#             "private": [
#                 {"addr": "10.0.0.98", "OS-EXT-IPS:type": "fixed"},
#             ]
#         }
#     }

#     api.block_storage.get_volume.return_value = FakeVolume(
#         "vol1",
#         metadata={"other": "true"}  # NOT ewccli
#     )

#     rc, msg = pre_delete_server(
#         openstack_backend=backend,
#         openstack_api=api,
#         federee="EUMETSAT",
#         server_name="vm1",
#         server_info=server_info,
#         dry_run=False,
#     )

#     assert rc == 0
#     assert "finished successfully" in msg
#     backend.detach_volumes_from_server.assert_not_called()


# def test_pre_delete_ewccli_volume_detach_delete():
#     backend = MagicMock()
#     api = MagicMock()

#     backend.remove_external_ip.return_value = (MagicMock(success=True), "ok")

#     server_info = {
#         "id": "server-123",
#         "attached_volumes": [{"id": "vol1"}],
#         "addresses": {
#             "private": [
#                 {"addr": "10.0.0.98", "OS-EXT-IPS:type": "fixed"},
#             ]
#         },
#         "metadata": {"deployed": "ewccli"},
#     }

#     api.block_storage.get_volume.return_value = FakeVolume(
#         "vol1",
#         metadata={"ewccli": "true", "server_name": "vm1"}
#     )

#     backend.detach_volumes_from_server.return_value = (
#         MagicMock(success=True),
#         ["vol1"],
#         "ok"
#     )

#     rc, msg = pre_delete_server(
#         openstack_backend=backend,
#         openstack_api=api,
#         federee="EUMETSAT",
#         server_name="vm1",
#         server_info=server_info,
#         dry_run=False,
#     )

#     assert rc == 0
#     assert "finished successfully" in msg
#     backend.detach_volumes_from_server.assert_called_once()


# def test_pre_delete_detach_failure():
#     backend = MagicMock()
#     api = MagicMock()

#     backend.remove_external_ip.return_value = (MagicMock(success=True), "ok")

#     server_info = {
#         "id": "server-123",
#         "attached_volumes": [{"id": "vol1"}],
#         "addresses": {
#             "private": [
#                 {"addr": "10.0.0.98", "OS-EXT-IPS:type": "fixed"},
#             ]
#         },
#         "metadata": {"deployed": "ewccli"},
#     }

#     api.block_storage.get_volume.return_value = FakeVolume(
#         "vol1",
#         metadata={"ewccli": "true", "server_name": "vm1"}
#     )

#     backend.detach_volumes_from_server.return_value = (
#         MagicMock(success=False),
#         [],
#         "detach failed"
#     )

#     rc, msg = pre_delete_server(
#         openstack_backend=backend,
#         openstack_api=api,
#         federee="EUMETSAT",
#         server_name="vm1",
#         server_info=server_info,
#         dry_run=False,
#     )

#     assert rc == 1
#     assert "detach/delete failed" in msg


# def test_pre_delete_dry_run():
#     backend = MagicMock()
#     api = MagicMock()

#     server_info = {
#         "id": "server-123",
#         "attached_volumes": [{"id": "vol1"}],
#         "addresses": {
#             "private": [
#                 {"addr": "10.0.0.98", "OS-EXT-IPS:type": "fixed"},
#             ]
#         },
#         "metadata": {"deployed": "ewccli"},
#     }

#     rc, msg = pre_delete_server(
#         openstack_backend=backend,
#         openstack_api=api,
#         federee="EUMETSAT",
#         server_name="vm1",
#         server_info=server_info,
#         dry_run=True,
#     )

#     assert rc == 0
#     assert "Dry Run" in msg
#     backend.detach_volumes_from_server.assert_not_called()
