#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC infra command."""

import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace
from ewccli.backends.openstack.backend_ostack import OpenstackBackend


# -------------------------
# Fixtures
# -------------------------

@pytest.fixture
def conn():
    """Mock OpenStack connection."""
    mock_conn = MagicMock()
    mock_conn.compute.images = MagicMock()
    mock_conn.compute.servers = MagicMock()
    return mock_conn


@pytest.fixture
def backend():
    return OpenstackBackend()


class FakeServer(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)

def make_server(**kwargs):
    return FakeServer(**kwargs)


# -------------------------
# Tests
# -------------------------

def test_basic_server(conn, backend):
    server = make_server(
        id="1",
        name="group2",
        status="ACTIVE",
        metadata={"deployed": "ewccli"},
        image={"id": "img1"},
        flavor={"original_name": "vm.a6000.4"},
        addresses={
            "private": [
                {"addr": "10.0.0.152", "OS-EXT-IPS:type": "fixed"}
            ]
        },
        security_groups=[{"name": "default"}],
    )

    image = make_server(id="img1", name="ubuntu")

    conn.compute.servers.return_value = [server]
    conn.compute.images.return_value = [image]

    result = backend.list_servers(conn, show_all=False, federee="EUMETSAT")

    assert "1" in result
    assert result["1"]["name"] == "group2"
    assert result["1"]["image"] == "ubuntu"
    assert "private-fixed" in result["1"]["networks"]
    assert result["1"]["security-groups"] == "default"


def test_security_groups_none(conn, backend):
    server = make_server(
        id="1",
        name="test",
        status="ACTIVE",
        metadata={"deployed": "ewccli"},
        image=None,
        flavor={"original_name": "vm"},
        addresses={},
        security_groups=None,
    )

    conn.compute.servers.return_value = [server]
    conn.compute.images.return_value = []

    result = backend.list_servers(conn, show_all=True)

    assert result["1"]["security-groups"] == ""


def test_multiple_networks(conn, backend):
    server = make_server(
        id="1",
        name="group1",
        status="ACTIVE",
        metadata={"deployed": "ewccli"},
        image=None,
        flavor={"original_name": "vm"},
        addresses={
            "private": [
                {"addr": "10.0.0.98", "OS-EXT-IPS:type": "fixed"},
                {"addr": "64.225.131.199", "OS-EXT-IPS:type": "floating"},
            ]
        },
        security_groups=[{"name": "default"}],
    )

    conn.compute.servers.return_value = [server]
    conn.compute.images.return_value = []

    result = backend.list_servers(conn, show_all=True, federee="EUMETSAT")

    networks = result["1"]["networks"]

    assert "private-fixed" in networks
    assert "private-floating" in networks


def test_filtered_by_metadata(conn, backend):
    server = make_server(
        id="1",
        name="ignored",
        status="ACTIVE",
        metadata={},  # no deployed=ewccli
        image=None,
        flavor={"original_name": "vm"},
        addresses={},
        security_groups=[],
    )

    conn.compute.servers.return_value = [server]
    conn.compute.images.return_value = []

    result = backend.list_servers(conn, show_all=False)

    assert result == {}


def test_show_all(conn, backend):
    server = make_server(
        id="1",
        name="included",
        status="ACTIVE",
        metadata={},
        image=None,
        flavor={"original_name": "vm"},
        addresses={},
        security_groups=[],
    )

    conn.compute.servers.return_value = [server]
    conn.compute.images.return_value = []

    result = backend.list_servers(conn, show_all=True)

    assert "1" in result


def test_error_server(conn, backend):
    server = make_server(
        id="1",
        name="broken",
        status="ERROR",
        metadata={"deployed": "ewccli"},
        image=None,
        flavor={"original_name": "vm"},
        addresses={},
        security_groups=None,
    )

    conn.compute.servers.return_value = [server]
    conn.compute.images.return_value = []

    result = backend.list_servers(conn, show_all=True)

    assert result["1"]["status"] == "ERROR"
