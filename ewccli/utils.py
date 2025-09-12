#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Utils."""

import os
import base64
import sys
import subprocess
from pathlib import Path
import secrets
import string
from datetime import datetime, timezone
from typing import Optional, Tuple, IO, List

import yaml
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from click import ClickException

from ewccli.configuration import config as ewc_hub_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


def save_cli_config(
    region: str,
    tenant_name: str,
    token: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
):
    """Save CLI configuration to YAML config file."""

    config_dir = ewc_hub_config.EWC_CLI_BASE_PATH
    config_dir.mkdir(parents=True, exist_ok=True)

    config_data = {
        "region": region,
        "tenant_name": tenant_name,
        "token": token,
    }

    if application_credential_id:
        config_data["application_credential_id"] = application_credential_id

    if application_credential_secret:
        config_data["application_credential_secret"] = application_credential_secret

    with open(config_dir / f"{region.lower()}-{tenant_name}.yaml", "w") as f:
        yaml.safe_dump(config_data, f)

    with open(
        config_dir
        / f"{ewc_hub_config.EWC_CLI_DEFAULT_REGION}-{ewc_hub_config.EWC_CLI_DEFAULT_TENANCY_NAME}.yaml",
        "w",
    ) as f:
        yaml.safe_dump(config_data, f)


def get_cli_config_path(
    region: str = ewc_hub_config.EWC_CLI_DEFAULT_REGION,
    tenant_name: str = ewc_hub_config.EWC_CLI_DEFAULT_TENANCY_NAME,
) -> Path:
    """Get CLI config path."""
    return ewc_hub_config.EWC_CLI_BASE_PATH / f"{region.lower()}-{tenant_name}.yaml"


def load_cli_config(
    region: str = ewc_hub_config.EWC_CLI_DEFAULT_REGION,
    tenant_name: str = ewc_hub_config.EWC_CLI_DEFAULT_TENANCY_NAME,
) -> dict:
    """Load config."""
    path = get_cli_config_path(region, tenant_name)

    if not path.exists():
        raise ClickException("No config found. Run `ewc login` first.")
    with open(path) as f:
        return yaml.safe_load(f)


def generate_random_id(length: int = 10):
    """Generate random ID."""
    characters = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(characters) for _ in range(length))
    date_part = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{date_part}-{random_part}"


def run_command_from_host(
    description: str,
    command: List[str],
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    dry_run: bool = False,
) -> Tuple[int, str]:
    """Run command with subprocess."""
    _LOGGER.debug(
        '"%s" -> exec command "%s" with timeout %s', description, command, timeout
    )

    if dry_run:
        return 0, "Dry run. No actions."

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,  # The output is decoded to a string
            shell=True,
            check=True,  # raise CalledProcessError if non-zero exit code
            cwd=cwd,
            env=env,
        )
        message = ""
        if result.stdout:
            message = f"📤 STDOUT:\n{result.stdout.strip()}"
        return result.returncode, message

    except subprocess.CalledProcessError as e:
        error_message = ""
        if e.stderr:
            error_message = f"📥 STDERR:\n{e.stderr.strip()}"
        return e.returncode, error_message


def run_command_from_host_live(
    description: str,
    command: str,
    timeout: Optional[str] = None,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    dry_run: bool = False,
):
    """Run a shell command, streaming output live to the terminal."""
    _LOGGER.info(
        '"%s" -> exec command "%s" with timeout %s', description, command, timeout
    )

    if dry_run:
        return 0, "Dry run. No actions."

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,  # for automatic decoding (Python 3.7+)
            bufsize=1,  # line-buffered
            cwd=cwd,
            env=env,
            shell=True,
        )
    except Exception as e:
        return 1, f"Failed to start process: {e}"

    def read_first_line(file: Optional[IO[str]]) -> Optional[str]:
        if file is None:
            return None
        return file.readline()

    try:
        while True:
            line = read_first_line(process.stdout)
            if line == "" and process.poll() is not None:
                break
            if line:
                _LOGGER.info(line, end="")

        return process.wait(), "Finishes successfully"

    except Exception as e:
        process.kill()
        return 1, f"\nError running command: {e}"


def download_items(force: bool = False):
    """Download items for the community hub."""
    # URL of the YAML file
    url = ewc_hub_config.EWC_CLI_HUB_ITEMS_URL

    # Path to ~/.ewccli
    config_dir = ewc_hub_config.EWC_CLI_BASE_PATH
    config_dir.mkdir(parents=True, exist_ok=True)

    # Destination file
    item_file = ewc_hub_config.EWC_CLI_HUB_ITEMS_PATH

    if item_file.exists() and not force:
        _LOGGER.debug(f"✅ Items file already exist at {item_file}. Skipping download.")
        return

    if force:
        _LOGGER.debug(
            f"✅ Items file already exist at {item_file}. Force enabled, redownloading it."
        )

    # Download the file
    try:
        # Add a timeout (e.g., 10 seconds)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        item_file.write_text(response.text)
        _LOGGER.debug(f"Downloaded to: {item_file}")
    except requests.Timeout:
        _LOGGER.error("⚠️ Request timed out.")
    except requests.RequestException as e:
        _LOGGER.error(f"❌ Failed to download file: {e}")


def load_ssh_private_key(encoded_key: Optional[str] = None):
    """Load SSH private key"""
    if encoded_key:
        try:
            private_key = base64.b64decode(encoded_key).decode("utf-8")
            # Use the private_key variable with ssh-add or other SSH tools
            return private_key
        except Exception as e:
            _LOGGER.error(f"Error decoding private key: {e}")
            sys.exit(1)
    else:
        _LOGGER.error("EWC_CLI_ENCODED_SSH_PRIVATE_KEY environment variable not set.")
        sys.exit(1)


def load_ssh_public_key(encoded_key: Optional[str] = None):
    """Load SSH public key"""
    # OpenSSH public keys have the format: <key-type> <base64-data> <comment>
    if encoded_key:
        try:
            public_key = base64.b64decode(encoded_key).decode("utf-8")
            # Use the public_key variable with ssh-add or other SSH tools
            return public_key
        except Exception as e:
            _LOGGER.error(f"Error decoding public key: {e}")
            sys.exit()
    else:
        _LOGGER.error("EWC_CLI_ENCODED_SSH_PUBLIC_KEY environment variable not set.")
        sys.exit(1)


def verify_private_key(private_key: str):
    """Verify SSH private key using cryptography."""
    error = False
    try:
        key_bytes = private_key.encode("utf-8")
        serialization.load_pem_private_key(
            key_bytes,
            password=None,  # If supporting encrypted keys, provide a password
            backend=default_backend(),
        )
        _LOGGER.info("✅ Private key is valid.")
    except ValueError as e:
        _LOGGER.error(f"❌ Invalid SSH key (ValueError): {e}")
        error = True
    except TypeError as e:
        _LOGGER.error(f"❌ SSH key error (TypeError): {e}")
        error = True
    except Exception as e:
        _LOGGER.error(f"❌ Unexpected error while verifying SSH key: {e}")
        error = True
    if error:
        sys.exit(1)


def save_ssh_key(ssh_key, path_key):
    """Store SSH key to the provided path."""
    # Define the file path to save the key
    key_path = os.path.expanduser(path_key)

    # Ensure the .ssh directory exists
    os.makedirs(os.path.dirname(key_path), exist_ok=True)

    # Write the private key to the file with secure permissions
    with open(key_path, "w") as key_file:
        key_file.write(ssh_key)

    # Set file permissions to 0600 (owner read/write only)
    os.chmod(key_path, 0o600)

    _LOGGER.debug(
        f"Key saved temporarely into the container to {key_path} with 0600 permissions."
    )


def save_ssh_keys(
    ssh_public_encoded: Optional[str] = None,
    ssh_private_encoded: Optional[str] = None,
):
    """Store SSH keys provided as encoded strings."""
    if ssh_public_encoded:
        _LOGGER.info("Using encoded public key provided.")
        public_key = load_ssh_public_key(encoded_key=ssh_public_encoded)
        save_ssh_key(
            ssh_key=public_key, path_key=ewc_hub_config.EWC_CLI_PUBLIC_SSH_KEY_PATH
        )

    if ssh_private_encoded:
        _LOGGER.info("Using encoded private key provided.")
        private_key = load_ssh_private_key(encoded_key=ssh_private_encoded)
        verify_private_key(private_key=private_key)
        save_ssh_key(
            ssh_key=private_key, path_key=ewc_hub_config.EWC_CLI_PRIVATE_SSH_KEY_PATH
        )


def generate_ssh_keypair(
    ssh_public_key_path: str,
    ssh_private_key_path: str,
):
    """Generate RSA SSH Key Pair and save to ~/.ssh"""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_key = private_key.public_key()
    public_key_ssh = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )

    # Ensure parent directories exist
    Path(ssh_private_key_path).parent.mkdir(parents=True, exist_ok=True)
    Path(ssh_public_key_path).parent.mkdir(parents=True, exist_ok=True)

    # Save private key
    with open(ssh_private_key_path, "wb") as f:
        f.write(private_key_pem)

    # Restrict permissions to owner only
    os.chmod(ssh_private_key_path, 0o600)

    # Save public key
    with open(ssh_public_key_path, "wb") as f:
        f.write(public_key_ssh)

    # Public key can be world-readable
    os.chmod(ssh_public_key_path, 0o644)

    _LOGGER.info(
        f"SSH key pair generated at {ssh_private_key_path} and {ssh_public_key_path}"
    )
