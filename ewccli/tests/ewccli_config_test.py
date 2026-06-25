#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Test config methods."""

import click
import pytest

# Import your new unified API
from ewccli.utils import (
    save_cli_profile,
    load_cli_profile,
    _resolve_profile,
    profile_exists,
    update_cli_profile_credentials,
    CredentialExpiredError,
)


@pytest.fixture
def profile_file_path(tmp_path):
    """Return a temporary path for profiles file."""
    return tmp_path / "profiles"


@pytest.fixture
def ssh_paths(tmp_path):
    """Create fake ssh key paths."""
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("private")
    pub.write_text("public")

    return str(priv), str(pub)


def test_save_and_load_profile(profile_file_path, ssh_paths):
    federee = "EUMETSAT"
    region = "WAW3-1"
    tenant_name = "TeamA"
    app_id = "ID1"
    app_secret = "SECRET1"
    kubeconfig_path = "/home/user/.ewccli/kubeconfigs/default.yaml"

    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee=federee,
        region=region,
        tenant_name=tenant_name,
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        application_credential_id=app_id,
        application_credential_secret=app_secret,
        kubeconfig_path=kubeconfig_path,
        profiles_file_path=str(profile_file_path),
    )

    profile_name = _resolve_profile(None, federee, region, tenant_name)

    data = load_cli_profile(
        profile=profile_name,
        profiles_file_path=str(profile_file_path),
    )

    assert data["profile"] == profile_name
    assert data["federee"] == federee
    assert data["tenant_name"] == tenant_name
    assert data["application_credential_id"] == app_id
    assert data["application_credential_secret"] == app_secret
    assert data["region"] == region
    assert data["ssh_private_key_path"] == ssh_private
    assert data["ssh_public_key_path"] == ssh_public
    assert data["kubeconfig_path"] == kubeconfig_path
    # No OIDC tokens are persisted
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "id_token" not in data
    assert "token_expires_at" not in data


def test_save_existing_profile_fails(profile_file_path, ssh_paths):
    federee = "EWC2"
    tenant_name = "TeamB"
    region = "reg"
    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee=federee,
        region=region,
        tenant_name=tenant_name,
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        profiles_file_path=str(profile_file_path),
    )

    with pytest.raises(click.Abort):
        save_cli_profile(
            federee=federee,
            region=region,
            tenant_name=tenant_name,
            ssh_private_key_path_to_save=ssh_private,
            ssh_public_key_path_to_save=ssh_public,
            profiles_file_path=str(profile_file_path),
        )


def test_load_missing_profile_raises(profile_file_path):
    with pytest.raises(click.Abort):
        load_cli_profile(
            profile="nonexistent",
            profiles_file_path=str(profile_file_path),
        )

    with pytest.raises(click.Abort):
        load_cli_profile(
            profiles_file_path=str(profile_file_path),
        )


def test_overwrite_profile_not_allowed(profile_file_path, ssh_paths):
    federee = "EWC5"
    tenant_name = "TeamE"
    region = "reg"
    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee=federee,
        region=region,
        tenant_name=tenant_name,
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        profiles_file_path=str(profile_file_path),
    )

    with pytest.raises(click.Abort):
        save_cli_profile(
            federee=federee,
            region=region,
            tenant_name=tenant_name,
            ssh_private_key_path_to_save=ssh_private,
            ssh_public_key_path_to_save=ssh_public,
            profiles_file_path=str(profile_file_path),
        )


def test_profile_exists_true(profile_file_path, ssh_paths):
    ssh_private, ssh_public = ssh_paths
    save_cli_profile(
        federee="EUMETSAT",
        region="WAW3-1",
        tenant_name="TeamA",
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        profiles_file_path=str(profile_file_path),
    )
    profile_name = _resolve_profile(None, "EUMETSAT", "WAW3-1", "TeamA")
    assert profile_exists(profile_name, str(profile_file_path)) is True


def test_profile_exists_false(profile_file_path):
    assert profile_exists("nonexistent", str(profile_file_path)) is False


def test_update_cli_profile_credentials(profile_file_path, ssh_paths):
    ssh_private, ssh_public = ssh_paths
    save_cli_profile(
        federee="EUMETSAT",
        region="WAW3-1",
        tenant_name="TeamA",
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        profiles_file_path=str(profile_file_path),
    )
    profile_name = _resolve_profile(None, "EUMETSAT", "WAW3-1", "TeamA")

    update_cli_profile_credentials(
        profile=profile_name,
        application_credential_id="new-app-id",
        application_credential_secret="new-app-secret",
        kubeconfig_path="/home/user/.ewccli/kubeconfigs/default.yaml",
        profiles_file_path=str(profile_file_path),
    )

    data = load_cli_profile(
        profile=profile_name,
        profiles_file_path=str(profile_file_path),
    )
    assert data["application_credential_id"] == "new-app-id"
    assert data["application_credential_secret"] == "new-app-secret"
    assert data["kubeconfig_path"] == "/home/user/.ewccli/kubeconfigs/default.yaml"
    # Original fields preserved
    assert data["federee"] == "EUMETSAT"
    assert data["tenant_name"] == "TeamA"


def test_update_cli_profile_credentials_missing_profile_raises(profile_file_path):
    from click import ClickException

    with pytest.raises(ClickException):
        update_cli_profile_credentials(
            profile="nonexistent",
            application_credential_id="new-app-id",
            profiles_file_path=str(profile_file_path),
        )


def test_credential_expired_error_is_exception():
    """CredentialExpiredError should be a catchable Exception."""
    assert issubclass(CredentialExpiredError, Exception)
    err = CredentialExpiredError("expired")
    assert str(err) == "expired"
