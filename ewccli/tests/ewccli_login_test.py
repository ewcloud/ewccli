#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC login command."""


import pytest
from pathlib import Path
from unittest.mock import patch
from configparser import ConfigParser
from click import ClickException

from ewccli.commands.login_command import check_and_generate_ssh_keys, init_command


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
# Login: existing profile -> refresh kubeconfig via KKP flow
# -----------------------------

_RAW_KUBECONFIG = """
apiVersion: v1
kind: Config
clusters:
- name: my-cluster
  cluster:
    server: https://abv9l8vmfm.kubermatic.k8s-val.example.com:6443
users:
- name: my-user
  user:
    auth-provider:
      name: oidc
      config:
        idp-issuer-url: https://k8s-val.example.com/dex
        client-id: kubermaticIssuer
        client-secret: secret
"""


def test_login_existing_profile_refreshes_kubeconfig(tmp_path, monkeypatch):
    """Re-login on an existing profile updates the kubeconfig path."""
    profiles_file = tmp_path / "profiles"

    cfg = ConfigParser()
    cfg["my-profile"] = {
        "federee": "",
        "region": "",
        "tenant_name": "",
        "ssh_public_key_path": str(tmp_path / "id_rsa.pub"),
        "ssh_private_key_path": str(tmp_path / "id_rsa"),
    }
    with open(profiles_file, "w") as f:
        cfg.write(f)

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
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KKP_PROJECT_ID",
        "a0f3891de6",
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KKP_CLUSTER_ID",
        "abv9l8vmfm",
    )

    with patch(
        "ewccli.backends.kkp.kubelogin.get_kkp_token", return_value="kkp-tok"
    ), patch(
        "ewccli.backends.kkp.network.ensure_kubelogin"
    ), patch(
        "ewccli.backends.kkp.kkp_client.KKPClient.get_oidc_kubeconfig",
        return_value=_RAW_KUBECONFIG,
    ):
        init_command(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            profile="my-profile",
            no_browser=True,
        )

    cfg2 = ConfigParser()
    cfg2.read(profiles_file)
    expected_kc = str(tmp_path / "kubeconfigs" / "my-profile.yaml")
    assert cfg2["my-profile"]["kubeconfig_path"] == expected_kc
    assert "access_token" not in cfg2["my-profile"]
    assert Path(expected_kc).exists()


# -----------------------------
# Login: new profile -> creates profile with kubeconfig
# -----------------------------

def test_login_new_profile_creates_profile(tmp_path, monkeypatch):
    """Login with a new profile name saves a fresh profile."""
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
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KKP_PROJECT_ID",
        "a0f3891de6",
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KKP_CLUSTER_ID",
        "abv9l8vmfm",
    )

    with patch(
        "ewccli.backends.kkp.kubelogin.get_kkp_token", return_value="kkp-tok"
    ), patch(
        "ewccli.backends.kkp.network.ensure_kubelogin"
    ), patch(
        "ewccli.backends.kkp.kkp_client.KKPClient.get_oidc_kubeconfig",
        return_value=_RAW_KUBECONFIG,
    ):
        init_command(
            ssh_public_key_path=str(pub),
            ssh_private_key_path=str(priv),
            profile="new-profile",
            no_browser=True,
        )

    cfg2 = ConfigParser()
    cfg2.read(profiles_file)
    assert "new-profile" in cfg2
    expected_kc = str(tmp_path / "kubeconfigs" / "new-profile.yaml")
    assert cfg2["new-profile"]["kubeconfig_path"] == expected_kc
    assert "access_token" not in cfg2["new-profile"]
    assert Path(expected_kc).exists()


# -----------------------------
# Login: missing project/cluster IDs -> ClickException
# -----------------------------

def test_login_missing_project_id_raises(tmp_path, monkeypatch):
    """If EWC_CLI_KKP_PROJECT_ID is unset, login fails with a clear error."""
    profiles_file = tmp_path / "profiles"
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"
    priv.write_text("private")
    pub.write_text("public")

    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_PROFILES_PATH",
        profiles_file,
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KKP_PROJECT_ID",
        None,
    )
    monkeypatch.setattr(
        "ewccli.commands.login_command.ewc_hub_config.EWC_CLI_KKP_CLUSTER_ID",
        "abv9l8vmfm",
    )

    with patch(
        "ewccli.backends.kkp.kubelogin.get_kkp_token", return_value="kkp-tok"
    ), patch(
        "ewccli.backends.kkp.network.ensure_kubelogin"
    ):
        with pytest.raises(ClickException, match="EWC_CLI_KKP_PROJECT_ID"):
            init_command(
                ssh_public_key_path=str(pub),
                ssh_private_key_path=str(priv),
                profile="x",
                no_browser=True,
            )
