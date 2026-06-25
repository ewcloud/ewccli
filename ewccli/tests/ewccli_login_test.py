#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC login command."""


import base64
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click import ClickException

from ewccli.commands.login_command import check_and_generate_ssh_keys, init_command


def _make_jwt(sub: str = "user-123") -> str:
    """Build a fake (unsigned) JWT with the given sub claim."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


# -----------------------------
# Case 1: both keys exist & match
# -----------------------------
def test_existing_matching_keys(tmp_path, monkeypatch):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("private")
    pub.write_text("public")

    # Patch where function is USED
    monkeypatch.setattr(
        "ewccli.commands.login_command.check_ssh_keys_match",
        lambda ssh_private_key_path, ssh_public_key_path: True,
    )

    result_priv, result_pub = check_and_generate_ssh_keys(
        ssh_public_key_path=str(pub),
        ssh_private_key_path=str(priv),
        resolved_profile="testprofile",
    )

    assert result_priv == str(priv)
    assert result_pub == str(pub)


# -----------------------------
# Case 1b: keys exist but mismatch
# -----------------------------
def test_existing_mismatching_keys(tmp_path, monkeypatch):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("private")
    pub.write_text("public")

    monkeypatch.setattr(
        "ewccli.commands.login_command.check_ssh_keys_match",
        lambda ssh_private_key_path, ssh_public_key_path: False,
    )

    with pytest.raises(ClickException):
        check_and_generate_ssh_keys(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            resolved_profile="testprofile",
        )


# -----------------------------
# Case 2: both keys missing -> user generates
# -----------------------------
def test_missing_keys_generate(tmp_path, monkeypatch):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    # Patch click.confirm in login_command
    monkeypatch.setattr(
        "ewccli.commands.login_command.click.confirm",
        lambda *args, **kwargs: True,
    )

    # Fake generate now only takes resolved_profile
    def fake_generate(resolved_profile):
        priv.write_text("generated private")
        pub.write_text("generated public")
        return priv, pub

    monkeypatch.setattr(
        "ewccli.commands.login_command.generate_ssh_keypair",
        fake_generate,
    )

    result_priv, result_pub = check_and_generate_ssh_keys(
        ssh_public_key_path=str(pub),
        ssh_private_key_path=str(priv),
        resolved_profile="profile",
    )

    assert Path(result_priv).exists()
    assert Path(result_pub).exists()


# -----------------------------
# Case 2b: both missing but user refuses generation
# -----------------------------
def test_missing_keys_user_declines(tmp_path, monkeypatch):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    monkeypatch.setattr(
        "ewccli.commands.login_command.click.confirm",
        lambda *args, **kwargs: False,
    )

    with pytest.raises(ClickException):
        check_and_generate_ssh_keys(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            resolved_profile="profile",
        )


# -----------------------------
# Case 3: only one key exists
# -----------------------------
def test_only_private_key_exists(tmp_path):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("private")

    with pytest.raises(ClickException):
        check_and_generate_ssh_keys(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            resolved_profile="profile",
        )


def test_only_public_key_exists(tmp_path):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    pub.write_text("public")

    with pytest.raises(ClickException):
        check_and_generate_ssh_keys(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            resolved_profile="profile",
        )


# -----------------------------
# Login: profile exists -> skip prompts, refresh credentials via OpenBao
# -----------------------------

def test_login_existing_profile_skips_prompts(tmp_path, monkeypatch):
    """When the profile already exists, federee/region/tenant_name prompts are skipped."""
    profiles_file = tmp_path / "profiles"

    # Pre-create a profile section
    from configparser import ConfigParser
    cfg = ConfigParser()
    cfg["my-profile"] = {
        "federee": "EUMETSAT",
        "region": "WAW3-1",
        "tenant_name": "my-tenant",
        "ssh_public_key_path": str(tmp_path / "id_rsa.pub"),
        "ssh_private_key_path": str(tmp_path / "id_rsa"),
    }
    profiles_file.write_text("")
    with open(profiles_file, "w") as f:
        cfg.write(f)

    # Write SSH key files so check_and_generate_ssh_keys finds them
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"
    priv.write_text("private")
    pub.write_text("public")

    monkeypatch.setattr(
        "ewccli.commands.login_command.check_ssh_keys_match",
        lambda ssh_private_key_path, ssh_public_key_path: True,
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_PROFILES_PATH",
        profiles_file,
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KUBECONFIG_PATH",
        tmp_path / "kubeconfigs",
    )

    # Mock keycloak_login — only access_token now
    access_token = _make_jwt("user-123")
    mock_kc_result = MagicMock()
    mock_kc_result.access_token = access_token

    # Mock OpenBao credential fetch
    mock_bao_creds = {
        "kubeconfig_path": str(tmp_path / "kubeconfigs" / "my-profile.yaml"),
        "application_credential_id": "bao-app-id",
        "application_credential_secret": "bao-app-secret",
    }

    select_federee_called = False
    select_region_called = False

    def fake_select_federee():
        nonlocal select_federee_called
        select_federee_called = True
        return "EUMETSAT"

    def fake_select_region(federee):
        nonlocal select_region_called
        select_region_called = True
        return "WAW3-1"

    with patch(
        "ewccli.backends.keycloak.keycloak_backend.keycloak_login",
        return_value=mock_kc_result,
    ), patch(
        "ewccli.commands.login_command.select_federee", side_effect=fake_select_federee
    ), patch(
        "ewccli.commands.login_command.select_region", side_effect=fake_select_region
    ), patch(
        "ewccli.commands.login_command._fetch_openbao_credentials",
        return_value=mock_bao_creds,
    ):
        init_command(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            tenant_name="",
            federee="",
            region="",
            profile="my-profile",
            no_browser=True,
        )

    # Prompts should NOT have been called
    assert not select_federee_called, "select_federee should not be called for existing profile"
    assert not select_region_called, "select_region should not be called for existing profile"

    # Credentials should be updated in the profile (no OIDC tokens)
    cfg2 = ConfigParser()
    cfg2.read(profiles_file)
    assert cfg2["my-profile"]["application_credential_id"] == "bao-app-id"
    assert cfg2["my-profile"]["application_credential_secret"] == "bao-app-secret"
    assert cfg2["my-profile"]["kubeconfig_path"] == str(tmp_path / "kubeconfigs" / "my-profile.yaml")
    # No OIDC tokens are stored
    assert "access_token" not in cfg2["my-profile"]
    assert "refresh_token" not in cfg2["my-profile"]


# -----------------------------
# Login: profile does not exist -> ask for federee/region/tenant_name
# -----------------------------

def test_login_new_profile_prompts_for_federee_region(tmp_path, monkeypatch):
    """When the profile does not exist, interactive prompts are shown."""
    profiles_file = tmp_path / "profiles"

    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"
    priv.write_text("private")
    pub.write_text("public")

    monkeypatch.setattr(
        "ewccli.commands.login_command.check_ssh_keys_match",
        lambda ssh_private_key_path, ssh_public_key_path: True,
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_PROFILES_PATH",
        profiles_file,
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KUBECONFIG_PATH",
        tmp_path / "kubeconfigs",
    )

    access_token = _make_jwt("user-456")
    mock_kc_result = MagicMock()
    mock_kc_result.access_token = access_token

    mock_bao_creds = {
        "kubeconfig_path": str(tmp_path / "kubeconfigs" / "new-profile.yaml"),
        "application_credential_id": "new-app-id",
        "application_credential_secret": "new-app-secret",
    }

    select_federee_called = False
    select_region_called = False

    def fake_select_federee():
        nonlocal select_federee_called
        select_federee_called = True
        return "EUMETSAT"

    def fake_select_region(federee):
        nonlocal select_region_called
        select_region_called = True
        return "WAW3-1"

    with patch(
        "ewccli.backends.keycloak.keycloak_backend.keycloak_login",
        return_value=mock_kc_result,
    ), patch(
        "ewccli.commands.login_command.select_federee", side_effect=fake_select_federee
    ), patch(
        "ewccli.commands.login_command.select_region", side_effect=fake_select_region
    ), patch(
        "ewccli.commands.login_command.click.prompt", return_value="my-tenant"
    ), patch(
        "ewccli.commands.login_command._fetch_openbao_credentials",
        return_value=mock_bao_creds,
    ):
        init_command(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            tenant_name="",
            federee="",
            region="",
            profile="new-profile",
            no_browser=True,
        )

    # Prompts SHOULD have been called
    assert select_federee_called, "select_federee should be called for new profile"
    assert select_region_called, "select_region should be called for new profile"

    # Profile should be created with credentials (no OIDC tokens)
    from configparser import ConfigParser
    cfg2 = ConfigParser()
    cfg2.read(profiles_file)
    assert "new-profile" in cfg2
    assert cfg2["new-profile"]["federee"] == "EUMETSAT"
    assert cfg2["new-profile"]["application_credential_id"] == "new-app-id"
    assert cfg2["new-profile"]["application_credential_secret"] == "new-app-secret"
    assert cfg2["new-profile"]["kubeconfig_path"] == str(tmp_path / "kubeconfigs" / "new-profile.yaml")
    # No OIDC tokens are stored
    assert "access_token" not in cfg2["new-profile"]
    assert "refresh_token" not in cfg2["new-profile"]
