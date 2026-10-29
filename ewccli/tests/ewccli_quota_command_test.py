#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for the EWC quota command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from ewccli.ewccli import cli


class MockProfile:
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def site_map(monkeypatch):
    """Fake site map so the auth URL resolves without touching the real config."""
    fake_site_map = {"eumetsat": {"r1": "http://fake-auth-url"}}
    monkeypatch.setattr(
        "ewccli.configuration.config.EWC_CLI_SITE_MAP", fake_site_map
    )
    monkeypatch.setattr(
        "ewccli.configuration.config.EWC_CLI_DEFAULT_PROFILE_NAME", "default"
    )
    return fake_site_map


@pytest.fixture
def mock_profile_store():
    with patch("ewccli.commands.quota_command.ProfileStore") as mock_store:
        mock_store.return_value.load.return_value = MockProfile(
            profile="test-profile",
            federee="eumetsat",
            region="r1",
            application_credential_id="fake-id",
            application_credential_secret="fake-secret",
        )
        yield mock_store


@pytest.fixture
def mock_backend():
    with patch("ewccli.commands.quota_command.OpenstackBackend") as mock_cls:
        mock_cls.return_value.connect.return_value = MagicMock()
        # Project ID resolves fine by default.
        mock_cls.get_project_id.return_value = "project-id-123"
        yield mock_cls


@pytest.fixture
def mock_quota_table():
    with patch("ewccli.commands.quota_command.show_quota_table") as mock_table:
        yield mock_table


# -------------------------
# Tests
# -------------------------


def test_quota_help(runner):
    result = runner.invoke(cli, ["quota", "--help"])

    assert result.exit_code == 0
    assert "Show Resources quota." in result.output


def test_quota_success(
    runner, site_map, mock_profile_store, mock_backend, mock_quota_table
):
    result = runner.invoke(cli, ["quota"])

    print("OUTPUT:", result.output)
    print("EXCEPTION:", result.exception)

    assert result.exit_code == 0
    mock_backend.return_value.connect.assert_called_once()
    mock_quota_table.assert_called_once_with(
        mock_backend.return_value, mock_backend.return_value.connect.return_value
    )


def test_quota_explicit_profile(
    runner, site_map, mock_profile_store, mock_backend, mock_quota_table
):
    result = runner.invoke(cli, ["quota", "--profile", "my-profile"])

    assert result.exit_code == 0
    mock_profile_store.return_value.load.assert_called_once_with(name="my-profile")


def test_quota_unknown_federee(runner, site_map, mock_profile_store, mock_backend):
    mock_profile_store.return_value.load.return_value = MockProfile(
        profile="test-profile",
        federee="unknown-federee",
        region="r1",
        application_credential_id="fake-id",
        application_credential_secret="fake-secret",
    )

    result = runner.invoke(cli, ["quota"])

    assert result.exit_code == 1
    assert "Unknown federee" in result.output


def test_quota_unknown_region(runner, site_map, mock_profile_store, mock_backend):
    mock_profile_store.return_value.load.return_value = MockProfile(
        profile="test-profile",
        federee="eumetsat",
        region="r99",
        application_credential_id="fake-id",
        application_credential_secret="fake-secret",
    )

    result = runner.invoke(cli, ["quota"])

    assert result.exit_code == 1
    assert "Unknown region" in result.output


def test_quota_connect_failure_adds_auth_hint(
    runner, site_map, mock_profile_store, mock_backend, mock_quota_table
):
    mock_backend.return_value.connect.side_effect = Exception(
        "Could not find Application Credential: ID123. (HTTP 401)"
    )

    result = runner.invoke(cli, ["quota"])

    assert result.exit_code == 1
    assert "Could not connect to Openstack" in result.output
    assert "~/.ewccli/profiles" in result.output
    mock_quota_table.assert_not_called()


def test_quota_connect_failure_without_auth_error_has_no_hint(
    runner, site_map, mock_profile_store, mock_backend, mock_quota_table
):
    mock_backend.return_value.connect.side_effect = Exception(
        "Connection refused by the server"
    )

    result = runner.invoke(cli, ["quota"])

    assert result.exit_code == 1
    assert "Could not connect to Openstack" in result.output
    assert "~/.ewccli/profiles" not in result.output


def test_quota_missing_project_id_fails_fast(
    runner, site_map, mock_profile_store, mock_backend, mock_quota_table
):
    mock_backend.get_project_id.return_value = None

    result = runner.invoke(cli, ["quota"])

    assert result.exit_code == 1
    assert "Could not determine the OpenStack project" in result.output
    assert "~/.ewccli/profiles" in result.output
    mock_quota_table.assert_not_called()


def test_quota_table_failure_wrapped(
    runner, site_map, mock_profile_store, mock_backend, mock_quota_table
):
    mock_quota_table.side_effect = Exception("boom (HTTP 401 Unauthorized)")

    result = runner.invoke(cli, ["quota"])

    assert result.exit_code == 1
    assert "Could not retrieve the quota information" in result.output
    assert "~/.ewccli/profiles" in result.output