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

from ewccli.ssh_keys_manager import SSHKeyManager, SSHKeyError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager() -> SSHKeyManager:
    return SSHKeyManager()


@pytest.fixture
def valid_private_key_pem() -> str:
    """Generate a valid RSA private key in PEM format."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


@pytest.fixture
def valid_public_key_openssh(valid_private_key_pem: str) -> str:
    """Derive a valid OpenSSH public key from the private key."""
    private_key = serialization.load_pem_private_key(
        valid_private_key_pem.encode("utf-8"), password=None
    )
    pub = private_key.public_key()
    return pub.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")


# ---------------------------------------------------------------------------
# Decoding tests
# ---------------------------------------------------------------------------

def test_load_private_encoded_success(manager, valid_private_key_pem):
    encoded = base64.b64encode(valid_private_key_pem.encode()).decode()
    result = manager.load_private_encoded(encoded)
    assert "BEGIN RSA PRIVATE KEY" in result


def test_load_private_encoded_missing(manager):
    with pytest.raises(SSHKeyError):
        manager.load_private_encoded(None)


def test_load_public_encoded_success(manager, valid_public_key_openssh):
    encoded = base64.b64encode(valid_public_key_openssh.encode()).decode()
    result = manager.load_public_encoded(encoded)
    assert result.startswith("ssh-")


def test_load_public_encoded_missing(manager):
    with pytest.raises(SSHKeyError):
        manager.load_public_encoded(None)


# ---------------------------------------------------------------------------
# Verification tests
# ---------------------------------------------------------------------------

def test_verify_private_valid(manager, valid_private_key_pem):
    manager.verify_private(valid_private_key_pem)  # Should not raise


def test_verify_private_invalid(manager):
    with pytest.raises(SSHKeyError):
        manager.verify_private("not a real key")


# ---------------------------------------------------------------------------
# Saving tests
# ---------------------------------------------------------------------------

def test_save_key_creates_file(manager, tmp_path):
    key_content = "dummy-key"
    path = tmp_path / "id_rsa"

    manager.save_key(key_content, path)

    assert path.exists()
    assert path.read_text() == key_content
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_save_encoded_keys(manager, tmp_path, valid_private_key_pem, valid_public_key_openssh):
    priv_path = tmp_path / "id_rsa"
    pub_path = tmp_path / "id_rsa.pub"

    encoded_priv = base64.b64encode(valid_private_key_pem.encode()).decode()
    encoded_pub = base64.b64encode(valid_public_key_openssh.encode()).decode()

    pub_written, priv_written = manager.save_encoded_keys(
        public_path=pub_path,
        private_path=priv_path,
        public_encoded=encoded_pub,
        private_encoded=encoded_priv,
    )

    assert pub_written is True
    assert priv_written is True
    assert priv_path.exists()
    assert pub_path.exists()


# ---------------------------------------------------------------------------
# Keypair generation tests
# ---------------------------------------------------------------------------

def test_generate_keypair(manager, tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "repo_path", tmp_path)

    priv_path, pub_path = manager.generate_keypair("pytest")

    assert priv_path.exists()
    assert pub_path.exists()

    assert "PRIVATE KEY" in priv_path.read_text()
    assert pub_path.read_text().startswith("ssh-")


# ---------------------------------------------------------------------------
# Existence + matching tests
# ---------------------------------------------------------------------------

def test_keys_exist(manager, tmp_path):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("x")
    pub.write_text("y")

    assert manager.keys_exist(priv, pub) is None


def test_keys_exist_missing(manager, tmp_path):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("x")
    # pub missing

    with pytest.raises(SSHKeyError):
        manager.keys_exist(priv, pub)


def test_keys_match_success(manager, tmp_path, valid_private_key_pem, valid_public_key_openssh):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text(valid_private_key_pem)
    pub.write_text(valid_public_key_openssh)

    assert manager.keys_match(priv, pub) is True


def test_keys_match_invalid(manager, tmp_path):
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("not a real key")
    pub.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQfake")

    with pytest.raises(SSHKeyError):
        manager.keys_match(priv, pub)
