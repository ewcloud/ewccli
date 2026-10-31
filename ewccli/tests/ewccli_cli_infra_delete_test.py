#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF
#

from __future__ import annotations

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from ewccli.ewccli import cli
from ewccli.enums import Federee, Region


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


@pytest.fixture(autouse=True)
def mock_profile_loader(monkeypatch):
    with patch("ewccli.commands.infra_command.ProfileStore.load") as mock_load:
        mock_load.return_value = MockProfile(
            profile="test-profile",
            auth_url="http://fake-auth-url",
            application_credential_id="fake-id",
            application_credential_secret="fake-secret",
            tenant_name="test-tenant",
            federee=Federee.EUMETSAT.value,
            region=Region.R1.value,
        )
        monkeypatch.setattr(
            "ewccli.configuration.config.EWC_CLI_SITE_MAP",
            {Federee.EUMETSAT.value: {Region.R1.value: "http://fake-auth-url"}},
        )
        yield mock_load


@pytest.fixture
def mock_openstack_connect():
    with patch("ewccli.commands.infra_command.OpenstackBackend.connect") as mock:
        yield mock


@pytest.fixture
def mock_pre_delete():
    with patch("ewccli.commands.infra_command.pre_delete_server") as mock:
        mock.return_value = (0, "[Pre delete] OK")
        yield mock


@pytest.fixture
def mock_delete_server():
    with patch("ewccli.commands.infra_command.OpenstackBackend.delete_server") as mock:
        mock.return_value = (MagicMock(), "Deleted my-server")
        yield mock


def test_delete_help(runner):
    result = runner.invoke(cli, ["infra", "delete", "--help"])

    assert result.exit_code == 0


def test_delete_server_not_found(
    runner, mock_openstack_connect, mock_pre_delete, mock_delete_server
):
    """A missing server must warn and exit cleanly, without deleting anything."""
    mock_openstack_connect.return_value.get_server.return_value = None

    with patch("ewccli.commands.infra_command._LOGGER") as mock_logger:
        result = runner.invoke(cli, ["infra", "delete", "my-server"])

    assert result.exit_code == 0, result.output
    mock_logger.warning.assert_called_once()
    assert "not found" in mock_logger.warning.call_args[0][0]
    mock_pre_delete.assert_not_called()
    mock_delete_server.assert_not_called()


def test_delete_connect_failure(runner, mock_openstack_connect):
    mock_openstack_connect.side_effect = Exception("boom")

    result = runner.invoke(cli, ["infra", "delete", "my-server"])

    assert result.exit_code != 0
    assert "Could not connect to Openstack" in result.output


def test_delete_get_server_failure(runner, mock_openstack_connect):
    mock_openstack_connect.return_value.get_server.side_effect = Exception("gone")

    result = runner.invoke(cli, ["infra", "delete", "my-server"])

    assert result.exit_code != 0
    assert "Could not retrieve server my-server" in result.output


def test_delete_pre_delete_exception(
    runner, mock_openstack_connect, mock_pre_delete, mock_delete_server
):
    mock_pre_delete.side_effect = Exception("detach failed")

    result = runner.invoke(cli, ["infra", "delete", "my-server"])

    assert result.exit_code != 0
    assert "Pre-delete steps failed for server my-server" in result.output
    mock_delete_server.assert_not_called()


def test_delete_pre_delete_failure_rc(
    runner, mock_openstack_connect, mock_pre_delete, mock_delete_server
):
    """A non-zero pre-delete status must abort before the actual deletion."""
    mock_pre_delete.return_value = (1, "no IPs identified")

    result = runner.invoke(cli, ["infra", "delete", "my-server"])

    assert result.exit_code != 0
    assert "no IPs identified" in result.output
    mock_delete_server.assert_not_called()


def test_delete_success(
    runner, mock_openstack_connect, mock_pre_delete, mock_delete_server
):
    result = runner.invoke(cli, ["infra", "delete", "my-server"])

    assert result.exit_code == 0, result.output

    mock_pre_delete.assert_called_once()
    pre_kwargs = mock_pre_delete.call_args.kwargs
    assert pre_kwargs["server_name"] == "my-server"
    assert pre_kwargs["federee"] == Federee.EUMETSAT.value
    assert pre_kwargs["dry_run"] is False

    mock_delete_server.assert_called_once()
    del_kwargs = mock_delete_server.call_args.kwargs
    assert del_kwargs["server_name"] == "my-server"
    assert del_kwargs["force"] is False
    assert del_kwargs["dry_run"] is False


def test_delete_force_dry_run_flags(
    runner, mock_openstack_connect, mock_pre_delete, mock_delete_server
):
    result = runner.invoke(
        cli, ["infra", "delete", "my-server", "--force", "--dry-run"]
    )

    assert result.exit_code == 0, result.output
    assert mock_pre_delete.call_args.kwargs["dry_run"] is True
    del_kwargs = mock_delete_server.call_args.kwargs
    assert del_kwargs["force"] is True
    assert del_kwargs["dry_run"] is True


def test_delete_env_var_server_name(
    runner, mock_openstack_connect, mock_pre_delete, mock_delete_server
):
    """EWC_CLI_OS_SERVER_NAME overrides the positional server name."""
    result = runner.invoke(
        cli,
        ["infra", "delete", "my-server"],
        env={"EWC_CLI_OS_SERVER_NAME": "other-server"},
    )

    assert result.exit_code == 0, result.output
    get_kwargs = mock_openstack_connect.return_value.get_server.call_args.kwargs
    assert get_kwargs["name_or_id"] == "other-server"
    assert mock_delete_server.call_args.kwargs["server_name"] == "other-server"