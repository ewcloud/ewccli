#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

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

    with patch("ewccli.commands.hub.hub_command.load_cli_profile") as mock_load:
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
@pytest.fixture(autouse=True)
def mock_ctx_obj():
    with patch("ewccli.commands.hub.hub_command.categorize_item_inputs") as m1, \
         patch("ewccli.commands.hub.hub_command.check_missing_required_inputs") as m2:

        m1.return_value = ([], [])
        m2.return_value = []

        yield


# -----------------------------
# CLI tests
# -----------------------------
def test_deploy_help(runner):
    result = runner.invoke(cli, ["hub", "deploy", "--help"])
    assert result.exit_code == 0


def test_deploy_missing_item(runner):
    result = runner.invoke(cli, ["hub", "deploy"])
    assert result.exit_code != 0


def test_deploy_dry_run_minimal(runner):
    result = runner.invoke(
        cli,
        ["hub", "deploy", "ssh-bastion-flavour", "--dry-run"],
        obj={
            "items": {
                "ssh-bastion-flavour": {
                    "cli": {"inputs": []}
                }
            }
        },
    )
    print(result.output)
    print(result.exception)

    assert result.exit_code == 0


def test_deploy_with_ssh_paths(runner, tmp_path, valid_private_key_pem, valid_public_key_openssh):
    pub_key = tmp_path / "id_rsa.pub"
    priv_key = tmp_path / "id_rsa"

    pub_key.write_text(valid_public_key_openssh)
    priv_key.write_text(valid_private_key_pem)

    result = runner.invoke(
        cli,
        [
            "hub",
            "deploy",
            "ssh-bastion-flavour",
            "--ssh-public-key-path",
            str(pub_key),
            "--ssh-private-key-path",
            str(priv_key),
            "--dry-run",
        ],
        obj={
            "items": {
                "ssh-bastion-flavour": {
                    "cli": {"inputs": []}
                }
            }
        },
    )

    assert result.exit_code == 0


def test_deploy_with_env_vars(runner, tmp_path, valid_private_key_pem, valid_public_key_openssh):
    pub_key = tmp_path / "id_rsa.pub"
    priv_key = tmp_path / "id_rsa"

    pub_key.write_text(valid_public_key_openssh)
    priv_key.write_text(valid_private_key_pem)

    result = runner.invoke(
        cli,
        ["hub", "deploy", "ssh-bastion-flavour", "--dry-run"],
        env={
            "EWC_CLI_SSH_PUBLIC_KEY_PATH": str(pub_key),
            "EWC_CLI_SSH_PRIVATE_KEY_PATH": str(priv_key),
        },
        obj={
            "items": {
                "ssh-bastion-flavour": {
                    "cli": {"inputs": []}
                }
            }
        },
    )

    assert result.exit_code == 0
