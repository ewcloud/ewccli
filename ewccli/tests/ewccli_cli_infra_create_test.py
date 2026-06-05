#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


from __future__ import annotations

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from ewccli.ewccli import cli

@pytest.fixture
def runner():
    return CliRunner()


# -----------------------------
# VALID SSH KEY FIXTURES
# -----------------------------
@pytest.fixture
def valid_private_key_pem() -> str:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


@pytest.fixture
def valid_public_key_openssh(valid_private_key_pem: str) -> str:
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(
        valid_private_key_pem.encode("utf-8"), password=None
    )
    pub = private_key.public_key()
    return pub.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")


# -----------------------------
# Mock profile loader globally
# -----------------------------
@pytest.fixture(autouse=True)
def mock_profile_loader(tmp_path, valid_private_key_pem, valid_public_key_openssh):
    pub_key = tmp_path / "id_rsa.pub"
    priv_key = tmp_path / "id_rsa"

    # ✅ write VALID keys
    pub_key.write_text(valid_public_key_openssh)
    priv_key.write_text(valid_private_key_pem)

    with patch("ewccli.commands.hub.hub_command.ProfileStore.load") as mock_load:
        mock_load.return_value = {
            "profile": "test-profile",
            "auth_url": "http://fake-auth-url",
            "application_credential_id": "fake-id",
            "application_credential_secret": "fake-secret",
            "tenant_name": "test-tenant",
            "federee": "test-federee",
            "ssh_public_key_path": str(pub_key),
            "ssh_private_key_path": str(priv_key),
        }
        yield mock_load

# -----------------------------
# Mock ctx.obj (CRITICAL)
# -----------------------------
@pytest.fixture
def mock_ctx(tmp_path, valid_private_key_pem, valid_public_key_openssh):
    pub = tmp_path / "id_rsa.pub"
    priv = tmp_path / "id_rsa"

    pub.write_text(valid_public_key_openssh)
    priv.write_text(valid_private_key_pem)

    ctx = MagicMock()
    ctx.cli_profile = {
        "federee": "test-fed",
        "ssh_public_key_path": str(pub),
        "ssh_private_key_path": str(priv),
    }

    ctx.openstack_backend = MagicMock()
    ctx.openstack_backend.connect.return_value = MagicMock()

    return ctx


# -----------------------------
# Patch decorators to pass ctx
# -----------------------------
@pytest.fixture(autouse=True)
def patch_infra_decorators(monkeypatch):
    monkeypatch.setattr("ewccli.commands.infra_command.infra_context", lambda f: f)
    monkeypatch.setattr("ewccli.commands.infra_command.ssh_options", lambda f: f)
    monkeypatch.setattr("ewccli.commands.infra_command.ssh_options_encoded", lambda f: f)
    monkeypatch.setattr("ewccli.commands.infra_command.openstack_options", lambda f: f)
    monkeypatch.setattr("ewccli.commands.infra_command.openstack_optional_options", lambda f: f)

# -----------------------------
# Patch create_server_command
# -----------------------------
@pytest.fixture
def mock_create_server():
    with patch("ewccli.commands.infra_command.create_server_command") as mock:
        mock.return_value = (
            0,
            "OK",
            {
                "internal_ip_machine": "10.0.0.5",
                "external_ip_machine": "1.2.3.4",
                "normalized_image_name": "ubuntu-22",
            },
        )
        yield mock


# -----------------------------
# TESTS
# -----------------------------
def test_create_help(runner, patch_infra_decorators):
    result = runner.invoke(cli, ["infra", "create", "--help"])
    assert result.exit_code == 0


def test_create_dry_run(runner, mock_ctx, mock_create_server):
    result = runner.invoke(
        cli,
        ["infra", "create", "my-server", "--dry-run"],
        obj=mock_ctx,
    )
    assert result.exit_code == 0
    assert "Dry run enabled" in result.output


def test_create_with_ssh_paths(
    runner, tmp_path, valid_private_key_pem, valid_public_key_openssh, mock_ctx, mock_create_server
):
    pub = tmp_path / "id_rsa.pub"
    priv = tmp_path / "id_rsa"

    pub.write_text(valid_public_key_openssh)
    priv.write_text(valid_private_key_pem)

    result = runner.invoke(
        cli,
        [
            "infra",
            "create",
            "my-server",
            "--ssh-public-key-path",
            str(pub),
            "--ssh-private-key-path",
            str(priv),
            "--dry-run",
        ],
        obj=mock_ctx,
    )

    assert result.exit_code == 0


def test_create_openstack_failure(runner, mock_ctx):
    mock_ctx.openstack_backend.connect.side_effect = Exception("boom")

    result = runner.invoke(
        cli,
        ["infra", "create", "my-server"],
        obj=mock_ctx,
    )

    assert result.exit_code != 0
    assert "Could not connect to Openstack" in result.output


def test_create_missing_username_mapping(runner, mock_ctx, mock_create_server):
    # Force missing username
    with patch("ewccli.commands.infra_command.ewc_hub_config.EWC_CLI_IMAGES_USER", {}):
        result = runner.invoke(
            cli,
            ["infra", "create", "my-server"],
            obj=mock_ctx,
        )

        assert result.exit_code != 0
        assert "username for ubuntu-22 could not be identified" in result.output


def test_create_success(runner, mock_ctx, mock_create_server):
    result = runner.invoke(
        cli,
        ["infra", "create", "my-server"],
        obj=mock_ctx,
    )

    assert result.exit_code == 0
    assert "Deployment Complete" in result.output
    assert "ssh -i" in result.output
