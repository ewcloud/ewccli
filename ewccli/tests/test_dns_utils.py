#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC commands common methods."""

from unittest import mock
import socket

import pytest
from ewccli.commands.commons import build_dns_record_name, wait_for_dns_record


def test_build_dns_record_name_valid():
    """Should correctly build a DNS record name using the ewcloud pattern."""
    result = build_dns_record_name("server1", "tenancyA", "fra")
    assert result == "server1.tenancyA.fra.ewcloud.host"


@pytest.mark.parametrize(
    "server,tenancy,location",
    [
        (None, "t1", "fra"),
        ("srv", "", "fra"),
        ("srv", "t1", None),
    ],
)
def test_build_dns_record_name_invalid_args(server, tenancy, location):
    """Should raise ValueError when any argument is missing or empty."""
    with pytest.raises(ValueError):
        build_dns_record_name(server, tenancy, location)


@mock.patch("socket.gethostbyname")
@mock.patch("time.sleep", return_value=None)  # skip real sleeping
def test_wait_for_dns_record_success(mock_sleep, mock_gethost):
    """Should return True when DNS resolves to the expected IP."""
    mock_gethost.return_value = "1.2.3.4"
    assert wait_for_dns_record("example.com", "1.2.3.4", interval=1, timeout_minutes=0.01)


@mock.patch("socket.gethostbyname", side_effect=socket.gaierror)
@mock.patch("time.sleep", return_value=None)
def test_wait_for_dns_record_timeout(mock_sleep, mock_gethost):
    """Should return False when DNS never resolves within timeout."""
    result = wait_for_dns_record("example.com", "1.2.3.4", interval=1, timeout_minutes=0.01)
    assert result is False


@mock.patch("socket.gethostbyname", side_effect=["2.2.2.2", "1.2.3.4"])
@mock.patch("time.sleep", return_value=None)
def test_wait_for_dns_record_eventual_success(mock_sleep, mock_gethost):
    """Should retry until the expected IP is resolved."""
    result = wait_for_dns_record("example.com", "1.2.3.4", interval=1, timeout_minutes=0.05)
    assert result is True
