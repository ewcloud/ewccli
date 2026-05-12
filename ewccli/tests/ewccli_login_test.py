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
from ewccli.ssh_keys_manager import SSHKeyError
from ewccli.commands.login_command import check_and_generate_ssh_keys


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
        "ewccli.ssh_keys_manager.SSHKeyManager.keys_match",
        lambda *args, **kwargs: True,
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
        "ewccli.ssh_keys_manager.SSHKeyManager.keys_match",
        lambda *args, **kwargs: (_ for _ in ()).throw(SSHKeyError("mismatch")),
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

    monkeypatch.setattr(
        "ewccli.commands.login_command.click.confirm",
        lambda *args, **kwargs: True,
    )

    def fake_generate(self, resolved_profile):
        priv.write_text("generated private")
        pub.write_text("generated public")
        return str(priv), str(pub)

    monkeypatch.setattr(
        "ewccli.ssh_keys_manager.SSHKeyManager.generate_keypair",
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
