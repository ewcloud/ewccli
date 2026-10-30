#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from unittest.mock import patch

from ewccli.profile import ProfileStore
from ewccli.ewccli import cli
from ewccli.enums import Federee, Region


class FakeProfile(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)


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

    # write VALID keys
    pub_key.write_text(valid_public_key_openssh)
    priv_key.write_text(valid_private_key_pem)

    fake_profile = FakeProfile(
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

    with patch("ewccli.commands.hub.hub_command.ProfileStore.load") as mock_load:
        mock_load.return_value = fake_profile
        yield mock_load


# -----------------------------
# Mock ctx.obj (CRITICAL)
# -----------------------------
@pytest.fixture(autouse=True)
def mock_ctx_obj():
    with (
        patch("ewccli.commands.hub.hub_command.categorize_item_inputs") as m1,
        patch("ewccli.commands.hub.hub_command.check_missing_required_inputs") as m2,
    ):
        m1.return_value = ([], [])
        m2.return_value = []

        yield


# -----------------------------
# CLI tests
# -----------------------------
def test_deploy_help(runner):
    result = runner.invoke(cli, ["hub", "deploy", "--help"])
    assert result.exit_code == 0


def test_deploy_dry_run_minimal(runner):

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
            ["hub", "deploy", "ssh-bastion-flavour", "--dry-run"],
            # obj={"items": {"ssh-bastion-flavour": {"cli": {"inputs": []}}}},
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


def test_deploy_ssh_flags_removed(runner, tmp_path, valid_private_key_pem, valid_public_key_openssh):
    """SSH key flags are login-only now (issue #188): hub deploy must reject them."""
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
        obj={"items": {"ssh-bastion-flavour": {"cli": {"inputs": []}}}},
    )

    assert result.exit_code != 0
    # rich_click renders usage errors in a panel; just verify the flag is rejected.
    assert "--ssh-public-key-path" in result.output or "option" in result.output.lower()


def test_deploy_uses_profile_ssh_keys(
    runner, tmp_path, valid_private_key_pem, valid_public_key_openssh
):
    """hub deploy resolves SSH keys from the profile created by `ewc login`."""
    pub_key = tmp_path / "id_rsa.pub"
    priv_key = tmp_path / "id_rsa"

    pub_key.write_text(valid_public_key_openssh)
    priv_key.write_text(valid_private_key_pem)

    result = runner.invoke(
        cli,
        ["hub", "deploy", "ssh-bastion-flavour", "--dry-run"],
        obj={"items": {"ssh-bastion-flavour": {"cli": {"inputs": []}}}},
    )

    assert result.exit_code == 0


# -----------------------------
# _validate_item EWCCLI-compatibility check (issue #197)
# -----------------------------
def _make_ctx(items):
    return SimpleNamespace(obj={"items": items})


COMPATIBLE_ITEM = {
    "annotations": {
        "others": "EWCCLI-compatible",
        "technology": "Ansible Playbook",
    },
    "cli": {"inputs": []},
}

NOT_COMPATIBLE_ITEM = {
    "annotations": {
        "others": "some-other-tag",
        "technology": "Ansible Playbook",
    },
    "cli": {"inputs": []},
}


def test_validate_item_accepts_compatible_item():
    from ewccli.commands.hub.hub_command import _validate_item

    ctx = _make_ctx({"good-item": COMPATIBLE_ITEM})
    assert _validate_item(ctx, None, "good-item") == "good-item"


def test_validate_item_rejects_non_compatible_item():
    from click import ClickException
    from ewccli.commands.hub.hub_command import _validate_item

    ctx = _make_ctx({"bad-item": NOT_COMPATIBLE_ITEM})
    with pytest.raises(ClickException) as exc:
        _validate_item(ctx, None, "bad-item")

    assert "not compatible with the EWC CLI" in str(exc.value)
    assert "EWCCLI-compatible" in str(exc.value)


def test_validate_item_rejects_unknown_item():
    from click import ClickException
    from ewccli.commands.hub.hub_command import _validate_item

    ctx = _make_ctx({"good-item": COMPATIBLE_ITEM})
    with pytest.raises(ClickException) as exc:
        _validate_item(ctx, None, "missing-item")

    assert "not available in the EWC Hub" in str(exc.value)


def test_validate_item_rejects_compatible_but_not_deployable():
    from click import ClickException
    from ewccli.commands.hub.hub_command import _validate_item

    item = {
        "annotations": {
            "others": "EWCCLI-compatible",
            "technology": "Some Unknown Technology",
        },
    }
    ctx = _make_ctx({"item": item})
    with pytest.raises(ClickException) as exc:
        _validate_item(ctx, None, "item")

    assert "not deployable" in str(exc.value)
