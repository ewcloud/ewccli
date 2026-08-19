#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC login command."""


import pytest
from pathlib import Path
from click import ClickException
from click.testing import CliRunner
from unittest.mock import patch

from configparser import ConfigParser
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ewccli.ewccli import cli
from ewccli.enums import Federee, Region
from ewccli.configuration import config as ewc_hub_config
from ewccli.commands.login_command import check_and_generate_ssh_keys, init_command
from ewccli.utils import delete_cli_profile, _resolve_profile


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

def test_validate_region_valid_eumetsat():
    import tempfile
    import subprocess
    runner = CliRunner()

    # Create temporary directory for SSH keys
    with tempfile.TemporaryDirectory() as tmpdir:
        priv = Path(tmpdir) / "id_rsa"
        pub = Path(tmpdir) / "id_rsa.pub"

        # Generate a real SSH keypair
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", str(priv), "-N", ""],
            check=True
        )

        federee = Federee.EUMETSAT.value
        region = Region.R1.value
        tenant_name = "dummy-dummy-dummy"

        result = runner.invoke(
            cli,
            [
                "login",
                "--application-credential-id", "dummy",
                "--application-credential-secret", "dummy",
                "--ssh-public-key-path", str(pub),
                "--ssh-private-key-path", str(priv),
                "--tenant-name", tenant_name,
                "--federee", federee,
                "--region", region,
            ]
        )

    resolved_profile = _resolve_profile(federee=federee, region=region, tenant_name=tenant_name)
    delete_cli_profile(profile=resolved_profile)

    print("OUTPUT:", result.output)
    print("EXCEPTION:", result.exception)
    print("TRACEBACK:", result.exc_info)
    assert result.exit_code == 0


def test_init_command_converts_path_objects_to_strings_without_prompt(tmp_path):
    # --- Generate a REAL RSA keypair in Python ---
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )

    # --- Write valid keys to tmp_path ---
    fake_priv = tmp_path / "id_rsa"
    fake_pub = tmp_path / "id_rsa.pub"

    fake_priv.write_bytes(private_bytes)
    fake_pub.write_bytes(public_bytes)

    # --- Inputs ---
    federee = Federee.EUMETSAT.value
    region = Region.R1.value
    tenant_name = "dummy-tenant"

    # --- Direct call: no CLI runner, no stdin, no ssh-keygen ---
    exit_code = init_command(
        application_credential_id="dummy",
        application_credential_secret="dummy",
        ssh_public_key_path=str(fake_pub),
        ssh_private_key_path=str(fake_priv),
        tenant_name=tenant_name,
        federee=federee,
        region=region,
        profile=None,
    )

    assert exit_code == 0

    # --- Load saved profile ---
    resolved_profile = _resolve_profile(
        federee=federee,
        region=region,
        tenant_name=tenant_name
    )

    cfg = ConfigParser()
    cfg.read(ewc_hub_config.EWC_CLI_PROFILES_PATH)

    saved_priv = cfg.get(resolved_profile, "ssh_private_key_path")
    saved_pub = cfg.get(resolved_profile, "ssh_public_key_path")

    # --- Assertions: conversion to string ---
    assert isinstance(saved_priv, str)
    assert isinstance(saved_pub, str)

    assert saved_priv.endswith("id_rsa")
    assert saved_pub.endswith("id_rsa.pub")

    # --- Cleanup ---
    delete_cli_profile(profile=resolved_profile)
