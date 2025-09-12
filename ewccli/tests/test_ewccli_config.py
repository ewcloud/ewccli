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

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import (
    save_cli_config,
    get_cli_config_path,
    load_cli_config,
)


@pytest.fixture
def temp_config_dir(monkeypatch):
    """
    Fixture that provides a temporary directory for CLI config files.

    It monkeypatches `ewc_hub_config.EWC_CLI_BASE_PATH` to point to a temp directory
    so that tests do not interfere with the real filesystem.

    Returns:
        Path: Path to the temporary directory.
    """
    tmpdir = Path(tempfile.mkdtemp())
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_BASE_PATH", tmpdir)

    # Ensure default region/tenant are predictable in tests
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_DEFAULT_REGION", "default-region")
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_DEFAULT_TENANCY_NAME", "default-tenant")

    return tmpdir


def test_save_cli_config_creates_files(temp_config_dir):
    """
    Test that `save_cli_config` creates both the region/tenant-specific config
    file and the default config file.

    Verifies:
        - Files exist in the expected directory.
        - YAML content includes region, tenant, and token values.
    """
    region = "TestRegion"
    tenant = "TestTenant"
    token = "secret-token"

    save_cli_config(region=region, tenant_name=tenant, token=token)

    # Expected output files
    specific_file = temp_config_dir / f"{region.lower()}-{tenant}.yaml"
    default_file = temp_config_dir / "default-region-default-tenant.yaml"

    assert specific_file.exists()
    assert default_file.exists()

    # Validate YAML content
    data = yaml.safe_load(specific_file.read_text())
    assert data["region"] == region
    assert data["tenant_name"] == tenant
    assert data["token"] == token


def test_save_cli_config_with_app_creds(temp_config_dir):
    """
    Test that `save_cli_config` includes application credential fields
    when they are provided as arguments.

    Verifies:
        - `application_credential_id` and `application_credential_secret` keys
          are present in the YAML file with the expected values.
    """
    save_cli_config(
        region="R1",
        tenant_name="T1",
        application_credential_id="id123",
        application_credential_secret="secret456",
    )

    config_file = temp_config_dir / "r1-T1.yaml"
    data = yaml.safe_load(config_file.read_text())

    assert data["application_credential_id"] == "id123"
    assert data["application_credential_secret"] == "secret456"


def test_save_cli_config_optional_fields_not_set(temp_config_dir):
    """
    Test that `save_cli_config` does not include optional credential fields
    when they are not provided.

    Verifies:
        - `application_credential_id` and `application_credential_secret` keys
          are absent from the YAML file.
    """
    save_cli_config(region="R2", tenant_name="T2")

    config_file = temp_config_dir / "r2-T2.yaml"
    data = yaml.safe_load(config_file.read_text())

    assert "application_credential_id" not in data
    assert "application_credential_secret" not in data


def test_get_cli_config_path_returns_correct_path(temp_config_dir):
    """
    Test that `get_cli_config_path` constructs the expected YAML file path
    based on region and tenant values.
    """
    region = "EU"
    tenant = "TenantX"

    path = get_cli_config_path(region, tenant)
    expected = temp_config_dir / "eu-TenantX.yaml"

    assert path == expected


def test_load_cli_config_reads_yaml_file(temp_config_dir):
    """
    Test that `load_cli_config` reads and returns YAML config correctly.
    """
    region = "NA"
    tenant = "TenantY"
    path = get_cli_config_path(region, tenant)

    # Write a sample config
    config_data = {"region": region, "tenant_name": tenant, "token": "tok123"}
    path.write_text(yaml.safe_dump(config_data))

    loaded = load_cli_config(region=region, tenant_name=tenant)

    assert loaded == config_data


def test_load_cli_config_raises_if_missing(temp_config_dir):
    """
    Test that `load_cli_config` raises a ClickException if the config file is missing.
    """
    with pytest.raises(click.ClickException, match="No config found. Run `ewc login` first."):
        load_cli_config(region="nonexistent", tenant_name="ghost")
