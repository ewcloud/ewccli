#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""
SSH Key Management for EWC CLI.

Provides loading, decoding, verification, saving, and generation of SSH keys.
"""

from __future__ import annotations

import os
import base64
from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from ewccli.configuration import config as ewc_hub_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


class SSHKeyError(Exception):
    """Custom exception for SSH key operations."""


class SSHKeyManager:
    """
    Manage SSH key loading, decoding, verification, saving, and generation.
    """

    def __init__(self, repo_path: Path = ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH):
        self.repo_path = Path(repo_path)

    # ------------------------------------------------------------------
    # Decoding
    # ------------------------------------------------------------------

    def load_private_encoded(self, encoded: Optional[str]) -> str:
        """
        Decode a base64‑encoded private key.

        Raises
        ------
        SSHKeyError
            If the key is missing or invalid.
        """
        if encoded is None:
            raise SSHKeyError("Missing encoded private key")

        try:
            return base64.b64decode(encoded).decode("utf-8")
        except Exception as exc:
            raise SSHKeyError(f"Failed to decode private key: {exc}") from exc

    def load_public_encoded(self, encoded: Optional[str]) -> str:
        """
        Decode a base64‑encoded public key.

        Raises
        ------
        SSHKeyError
            If the key is missing or invalid.
        """
        if encoded is None:
            raise SSHKeyError("Missing encoded public key")

        try:
            return base64.b64decode(encoded).decode("utf-8")
        except Exception as exc:
            raise SSHKeyError(f"Failed to decode public key: {exc}") from exc

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_private(self, private_key: str) -> None:
        """
        Verify that a private key is valid.

        Raises
        ------
        SSHKeyError
            If the key is invalid or unsupported.
        """
        try:
            serialization.load_pem_private_key(
                private_key.encode("utf-8"),
                password=None,
                backend=default_backend(),
            )
        except Exception as exc:
            raise SSHKeyError(f"Invalid private key: {exc}") from exc

    def keys_match(self, private_path: Path, public_path: Path) -> bool:
        """
        Check whether a private key corresponds to a given public key.

        Returns
        -------
        bool
            True if the keys match.

        Raises
        ------
        SSHKeyError
            If files are missing or formats are invalid.
        """
        private_path = Path(private_path).expanduser()
        public_path = Path(public_path).expanduser()

        if not private_path.is_file():
            raise SSHKeyError(f"Private key file does not exist: {private_path}")
        if not public_path.is_file():
            raise SSHKeyError(f"Public key file does not exist: {public_path}")

        private_data = private_path.read_bytes()

        try:
            private_key = serialization.load_pem_private_key(
                private_data, password=None
            )
        except ValueError:
            try:
                private_key = serialization.load_ssh_private_key(
                    private_data, password=None
                )
            except ValueError as exc:
                raise SSHKeyError("Unsupported or invalid private key format") from exc

        derived_public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )

        parts = public_path.read_text().strip().split()
        if len(parts) < 2:
            raise SSHKeyError(f"Invalid public key format: {public_path}")

        provided_public = " ".join(parts[:2]).encode()

        return bool(derived_public == provided_public)

    def keys_exist(self, ssh_public_key_path: Path, ssh_private_key_path: Path) -> None:
        """
        Ensure that both SSH key files exist.

        Raises
        ------
        SSHKeyError
            If one or both files are missing.
        """
        public_path = Path(ssh_public_key_path)
        private_path = Path(ssh_private_key_path)

        missing = []

        if not private_path.is_file():
            missing.append(
                f"🔒 [bold red]Missing Private Key:[/bold red] {private_path}"
            )

        if not public_path.is_file():
            missing.append(f"🔓 [bold red]Missing Public Key:[/bold red] {public_path}")

        missing_msg = (
            "\n".join(missing)
            + "\n\n"
            + "[bold yellow]Tip:[/bold yellow] You can run ewc login and create them.\n"
            + "[bold yellow]Tip:[/bold yellow] You can specify custom paths with:\n"
            + '[green]export EWC_CLI_SSH_PRIVATE_KEY_PATH="/path/to/id_rsa"[/green]\n'
            + '[green]export EWC_CLI_SSH_PUBLIC_KEY_PATH="/path/to/id_rsa.pub"[/green]'
        )

        if missing:
            raise SSHKeyError(missing_msg)

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save_key(self, key: str, path: Path) -> None:
        """
        Save a key to disk with secure permissions.
        """
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(key)
        os.chmod(path, 0o600)

    def save_encoded_keys(
        self,
        ssh_public_key_path: Path,
        ssh_private_key_path: Path,
        ssh_public_encoded: Optional[str],
        ssh_private_encoded: Optional[str],
    ) -> Tuple[bool, bool]:
        """
        Save base64‑encoded SSH keys to disk.

        Returns
        -------
        (bool, bool)
            Tuple indicating whether public and private keys were written.
        """
        public_written = False
        private_written = False

        # PUBLIC
        if ssh_public_encoded:
            public_key = self.load_public_encoded(ssh_public_encoded)
            self.save_key(public_key, ssh_public_key_path)
            public_written = True

        # PRIVATE
        if ssh_private_encoded:
            private_key = self.load_private_encoded(ssh_private_encoded)
            self.verify_private(private_key)
            self.save_key(private_key, ssh_private_key_path)
            private_written = True

        return public_written, private_written

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_keypair(self, profile_name: str) -> Tuple[Path, Path]:
        """
        Generate an RSA SSH keypair and save it under the repo path.

        Returns
        -------
        (Path, Path)
            Paths to the private and public key files.
        """
        self.repo_path.mkdir(parents=True, exist_ok=True)

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_ssh = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )

        private_path = self.repo_path / f"{profile_name}_id_rsa"
        public_path = self.repo_path / f"{profile_name}_id_rsa.pub"

        private_path.write_bytes(private_pem)
        os.chmod(private_path, 0o600)

        public_path.write_bytes(public_ssh)
        os.chmod(public_path, 0o644)

        _LOGGER.info(f"SSH keypair generated at {private_path} and {public_path}")

        return private_path, public_path
