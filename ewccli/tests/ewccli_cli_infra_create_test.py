#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF
#

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from ewccli.profile import ProfileStore
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


@pytest.fixture(autouse=True)
def mock_profile_loader(
    tmp_path, valid_private_key_pem, valid_public_key_openssh, monkeypatch
):
    pub_key = tmp_path / "id_rsa.pub"
    priv_key = tmp_path / "id_rsa"

    pub_key.write_text(valid_public_key_openssh)
    priv_key.write_text(valid_private_key_pem)

    with patch("ewccli.commands.hub.hub_command.ProfileStore.load") as mock_load:
        mock_load.return_value = MockProfile(
            profile="test-profile",
            auth_url="http://fake-auth-url",
            application_credential_id="fake-id",
            application_credential_secret="fake-secret",
            tenant_name="test-tenant",
            federee=Federee.EUMETSAT.value,
            region=Region.R1.value,
            ssh_public_key_path=str(pub_key),
            ssh_private_key_path=str(priv_key),
        )
        monkeypatch.setattr(
            "ewccli.configuration.config.allowed_regions",
            lambda federee: [Region.R1.value],
        )
        monkeypatch.setattr(
            "ewccli.configuration.config.EWC_CLI_SITE_MAP",
            {Federee.EUMETSAT.value: {Region.R1.value: "http://fake-auth-url"}},
        )
        yield mock_load


@pytest.fixture(autouse=True)
def patch_infra_decorators(monkeypatch):
    monkeypatch.setattr("ewccli.commands.infra_command.ssh_options", lambda f: f)
    monkeypatch.setattr(
        "ewccli.commands.infra_command.ssh_options_encoded", lambda f: f
    )


@pytest.fixture
def mock_create_server():
    with patch("ewccli.commands.infra_command.create_server_command") as mock:
        mock.return_value = (
            0,
            "OK",
            {
                "internal_ip_machine": "10.0.0.5",
                "external_ip_machine": "1.2.3.4",
                "normalized_image_name": "Ubuntu-22.04",
            },
        )
        yield mock


@pytest.fixture
def mock_openstack_connect():
    with patch("ewccli.commands.infra_command.OpenstackBackend.connect") as mock_conn:
        mock_conn.return_value = MagicMock()
        yield mock_conn


def test_create_help(runner):
    result = runner.invoke(cli, ["infra", "create", "--help"])

    print("OUTPUT:", result.output)
    print("EXCEPTION:", result.exception)
    print("TRACEBACK:", result.exc_info)

    assert result.exit_code == 0


def test_create_dry_run(runner):

    # Create temporary directory for SSH keys
    with tempfile.TemporaryDirectory() as tmpdir:
        priv = Path(tmpdir) / "id_rsa"
        pub = Path(tmpdir) / "id_rsa.pub"

        # Generate a real SSH keypair
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", str(priv), "-N", ""],
            check=True,
        )

        federee = Federee.EUMETSAT.value
        region = Region.R1.value
        tenant_name = "dummy-dummy-dummy"

        result = runner.invoke(
            cli,
            [
                "login",
                "--application-credential-id",
                "dummy",
                "--application-credential-secret",
                "dummy",
                "--ssh-public-key-path",
                str(pub),
                "--ssh-private-key-path",
                str(priv),
                "--tenant-name",
                tenant_name,
                "--federee",
                federee,
                "--region",
                region,
            ],
        )

        result = runner.invoke(
            cli,
            ["infra", "create", "my-server", "--dry-run"],
        )

    profile = ProfileStore()
    resolved_profile = profile.resolve_name(
        federee=federee, region=region, tenant_name=tenant_name
    )
    profile.delete(name=resolved_profile)

    print("OUTPUT:", result.output)
    print("EXCEPTION:", result.exception)
    print("TRACEBACK:", result.exc_info)

    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_create_with_ssh_paths(
    runner,
    tmp_path,
    valid_private_key_pem,
    valid_public_key_openssh,
):

    
    # Create temporary directory for SSH keys
    with tempfile.TemporaryDirectory() as tmpdir:
        priv = Path(tmpdir) / "id_rsa"
        pub = Path(tmpdir) / "id_rsa.pub"

        # Generate a real SSH keypair
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", str(priv), "-N", ""],
            check=True,
        )

        federee = Federee.EUMETSAT.value
        region = Region.R1.value
        tenant_name = "dummy-dummy-dummy"

        result = runner.invoke(
            cli,
            [
                "login",
                "--application-credential-id",
                "dummy",
                "--application-credential-secret",
                "dummy",
                "--ssh-public-key-path",
                str(pub),
                "--ssh-private-key-path",
                str(priv),
                "--tenant-name",
                tenant_name,
                "--federee",
                federee,
                "--region",
                region,
            ],
        )

        result = runner.invoke(
            cli,
            [
                "infra",
                "create",
                "my-server",
                "--ssh-public-key-path",
                pub.as_posix(),
                "--ssh-private-key-path",
                priv.as_posix(),
                "--dry-run",
            ],
        )

    profile = ProfileStore()
    resolved_profile = profile.resolve_name(
        federee=federee, region=region, tenant_name=tenant_name
    )
    profile.delete(name=resolved_profile)

    print("OUTPUT:", result.output)
    print("EXCEPTION:", result.exception)
    print("TRACEBACK:", result.exc_info)

    assert result.exit_code == 0


def test_create_openstack_failure(runner):
    with patch("ewccli.commands.infra_command.OpenstackBackend.connect") as mock_conn:
        mock_conn.side_effect = Exception("boom")

        result = runner.invoke(
            cli,
            ["infra", "create", "my-server"],
        )

        assert result.exit_code != 0
        assert "Could not connect to Openstack" in result.output


def test_create_missing_username_mapping(runner, mock_create_server, mock_openstack_connect):
    with patch("ewccli.commands.infra_command.ewc_hub_config.EWC_CLI_IMAGES_USER", {}):
        result = runner.invoke(
            cli,
            ["infra", "create", "my-server"],
        )


        print("OUTPUT:", result.output)
        print("EXCEPTION:", result.exception)
        print("TRACEBACK:", result.exc_info)

        assert result.exit_code != 0
        assert "username for Ubuntu-22.04 could not be identified" in result.output


def test_create_success(runner, mock_create_server, mock_openstack_connect):
    result = runner.invoke(
        cli,
        ["infra", "create", "my-server"],
    )

    print("OUTPUT:", result.output)
    print("EXCEPTION:", result.exception)
    print("TRACEBACK:", result.exc_info)

    assert result.exit_code == 0
    assert "Deployment Complete" in result.output
    assert "ssh -i" in result.output
