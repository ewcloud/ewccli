#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Test ssh keys methods."""


import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import (
    load_ssh_private_key,
    load_ssh_public_key,
    verify_private_key,
    save_ssh_key,
    save_ssh_keys,
    generate_ssh_keypair,
)


@pytest.fixture
def valid_private_key_pem() -> str:
    """
    Fixture that generates a valid RSA private key in PEM format.

    Returns:
        str: PEM-encoded RSA private key.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


@pytest.fixture
def valid_public_key_openssh(valid_private_key_pem: str) -> str:
    """
    Fixture that derives a valid OpenSSH-formatted public key
    from the generated private key.

    Args:
        valid_private_key_pem (str): PEM-encoded private key.

    Returns:
        str: OpenSSH public key string.
    """
    private_key = serialization.load_pem_private_key(
        valid_private_key_pem.encode("utf-8"), password=None
    )
    pub = private_key.public_key()
    return pub.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")


def test_load_ssh_private_key_success(valid_private_key_pem):
    """
    Test that `load_ssh_private_key` decodes base64-encoded PEM correctly.
    """
    encoded = base64.b64encode(valid_private_key_pem.encode("utf-8")).decode("utf-8")
    result = load_ssh_private_key(encoded_key=encoded)
    assert "BEGIN RSA PRIVATE KEY" in result


def test_load_ssh_private_key_missing(monkeypatch):
    """
    Test that `load_ssh_private_key` exits with error when no key is provided.
    """
    with pytest.raises(SystemExit):
        load_ssh_private_key(encoded_key=None)


def test_load_ssh_public_key_success(valid_public_key_openssh):
    """
    Test that `load_ssh_public_key` decodes base64-encoded OpenSSH public key.
    """
    encoded = base64.b64encode(valid_public_key_openssh.encode("utf-8")).decode("utf-8")
    result = load_ssh_public_key(encoded_key=encoded)
    assert result.startswith("ssh-rsa")


def test_load_ssh_public_key_missing():
    """
    Test that `load_ssh_public_key` exits when key is not provided.
    """
    with pytest.raises(SystemExit):
        load_ssh_public_key(encoded_key=None)


def test_verify_private_key_valid(valid_private_key_pem):
    """
    Test that `verify_private_key` passes with a valid key.
    """
    # Should not raise SystemExit
    verify_private_key(valid_private_key_pem)


def test_verify_private_key_invalid():
    """
    Test that `verify_private_key` exits with error on invalid key.
    """
    with pytest.raises(SystemExit):
        verify_private_key("this is not a valid key")


def test_save_ssh_key_creates_file(tmp_path):
    """
    Test that `save_ssh_key` writes a file with correct permissions.
    """
    key_content = "dummy-key"
    path = tmp_path / "id_rsa"

    save_ssh_key(ssh_key=key_content, path_key=str(path))

    assert path.exists()
    assert path.read_text() == key_content
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_save_ssh_keys_writes_files(tmp_path, valid_private_key_pem, valid_public_key_openssh, monkeypatch):
    """
    Test that `save_ssh_keys` writes both private and public keys when provided.
    """
    priv_path = tmp_path / "id_rsa"
    pub_path = tmp_path / "id_rsa.pub"

    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_PRIVATE_SSH_KEY_PATH", str(priv_path))
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_PUBLIC_SSH_KEY_PATH", str(pub_path))

    encoded_priv = base64.b64encode(valid_private_key_pem.encode("utf-8")).decode("utf-8")
    encoded_pub = base64.b64encode(valid_public_key_openssh.encode("utf-8")).decode("utf-8")

    save_ssh_keys(ssh_public_encoded=encoded_pub, ssh_private_encoded=encoded_priv)

    assert priv_path.exists()
    assert pub_path.exists()


def test_generate_ssh_keypair_creates_files(tmp_path):
    """
    Test that `generate_ssh_keypair` creates private and public key files.
    """
    priv_path = tmp_path / "id_rsa"
    pub_path = tmp_path / "id_rsa.pub"

    generate_ssh_keypair(str(pub_path), str(priv_path))

    assert priv_path.exists()
    assert pub_path.exists()
    assert b"BEGIN RSA PRIVATE KEY" in priv_path.read_bytes()
    assert pub_path.read_text().startswith("ssh-rsa")
