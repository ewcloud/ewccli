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
    tenant_name = "TeamA"
    token = "tok1"
    app_id = "ID1"
    app_secret = "SECRET1"
    region = "us-east-1"

    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee=federee,
        tenant_name=tenant_name,
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        token=token,
        application_credential_id=app_id,
        application_credential_secret=app_secret,
        region=region,
        profiles_file_path=str(profile_file_path),
    )

    profile_name = _resolve_profile(None, federee, tenant_name)

    data = load_cli_profile(
        profile=profile_name,
        profiles_file_path=str(profile_file_path),
    )

    assert data["profile"] == profile_name
    assert data["federee"] == federee
    assert data["tenant_name"] == tenant_name
    assert data["token"] == token
    assert data["application_credential_id"] == app_id
    assert data["application_credential_secret"] == app_secret
    assert data["region"] == region
    assert data["ssh_private_key_path"] == ssh_private
    assert data["ssh_public_key_path"] == ssh_public


def test_save_existing_profile_fails(profile_file_path, ssh_paths):
    federee = "EWC2"
    tenant_name = "TeamB"
    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee,
        tenant_name,
        ssh_private,
        ssh_public,
        profiles_file_path=str(profile_file_path),
    )

    with pytest.raises(click.Abort):
        save_cli_profile(
            federee,
            tenant_name,
            ssh_private,
            ssh_public,
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
    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee,
        tenant_name,
        ssh_private,
        ssh_public,
        profiles_file_path=str(profile_file_path),
    )

    with pytest.raises(click.Abort):
        save_cli_profile(
            federee,
            tenant_name,
            ssh_private,
            ssh_public,
            profiles_file_path=str(profile_file_path),
        )
