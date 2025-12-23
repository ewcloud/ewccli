#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Test config methods."""

import tempfile
from pathlib import Path

import click
import yaml
import pytest

from configparser import ConfigParser
# Import your new unified API
from ewccli.utils import (
    save_cli_profile,
    save_default_login_profile,
    load_cli_profile,
    _resolve_profile,
)

@pytest.fixture
def profile_file_path(tmp_path):
    """Return a temporary path for profiles file."""
    return tmp_path / "profiles"


def test_save_and_load_profile(profile_file_path):
    federee = "EUMETSAT"
    tenant_name = "TeamA"
    token = "tok1"
    app_id = "ID1"
    app_secret = "SECRET1"
    region = "us-east-1"

    # Save profile
    save_cli_profile(
        federee=federee,
        tenant_name=tenant_name,
        token=token,
        application_credential_id=app_id,
        application_credential_secret=app_secret,
        region=region,
        profiles_file_path=str(profile_file_path),
    )

    profile_name = _resolve_profile(None, federee, tenant_name)

    # Load by profile
    data = load_cli_profile(profile=profile_name, profiles_file_path=str(profile_file_path))
    assert data["profile"] == profile_name
    assert data["federee"] == federee
    assert data["tenant_name"] == tenant_name
    assert data["token"] == token
    assert data["application_credential_id"] == app_id
    assert data["application_credential_secret"] == app_secret
    assert data["region"] == region


def test_save_existing_profile_fails(profile_file_path):
    federee = "EWC2"
    tenant_name = "TeamB"

    save_cli_profile(federee, tenant_name, profiles_file_path=str(profile_file_path))

    # Attempt to save again should raise click.Abort
    with pytest.raises(click.Abort):
        save_cli_profile(federee, tenant_name, profiles_file_path=str(profile_file_path))


def test_load_missing_profile_raises(profile_file_path):
    # Attempt to load a non-existent profile
    with pytest.raises(click.Abort):
        load_cli_profile(profile="nonexistent", profiles_file_path=str(profile_file_path))

    # Attempt to auto-resolve without federee/tenant_name → should raise
    with pytest.raises(click.Abort):
        load_cli_profile(profiles_file_path=str(profile_file_path))


def test_overwrite_profile_not_allowed(profile_file_path):
    federee = "EWC5"
    tenant_name = "TeamE"

    save_cli_profile(federee, tenant_name, profiles_file_path=str(profile_file_path))

    # Attempting to save again should fail
    with pytest.raises(click.Abort):
        save_cli_profile(federee, tenant_name, profiles_file_path=str(profile_file_path))