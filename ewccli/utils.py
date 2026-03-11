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
from typing import Optional, Tuple, IO, List, Dict

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from configparser import ConfigParser

import rich_click as click
from click import ClickException

from ewccli.configuration import config as ewc_hub_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


def _resolve_profile(
    profile: Optional[str] = None,
    federee: Optional[str] = None,
    tenant_name: Optional[str] = None,
) -> str:
    """Return explicit profile or auto-generate one using federee-tenant."""
    if profile is not None:
        return profile

    if not federee or not tenant_name:
        click.secho(
            "❌ Either 'profile' must be provided or both 'federee' and 'tenant_name'.",
            fg="red",
            bold=True,
        )
        raise click.Abort()

    return f"{federee.lower()}-{tenant_name.lower()}"


def save_default_login_profile(
    federee: str,
    tenant_name: str,
    ssh_private_key_path_to_save: str,
    ssh_public_key_path_to_save: str,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    region: Optional[str] = None,
    token: Optional[str] = None,
    profiles_file_path: Path = ewc_hub_config.EWC_CLI_PROFILES_PATH,
) -> None:
    """
    Save the default login profile to EWC_CLI_PROFILES_PATH only if it does not exist.
    If it already exists, do nothing (skip).

    Uses ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME as the profile name.
    """
    resolved_profile = _resolve_profile(
        profile=ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME,
    )

    cfg = ConfigParser()
    cfg.read(profiles_file_path)

    # Skip saving if the default profile already exists
    if resolved_profile in cfg:
        return

    # Save profile (reusing the unified save_cli_profile logic)

    save_cli_profile(
        federee=federee,
        tenant_name=tenant_name,
        ssh_private_key_path_to_save=ssh_private_key_path_to_save,
        ssh_public_key_path_to_save=ssh_public_key_path_to_save,
        profile=resolved_profile,
        token=token,
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
        region=region,
    )


def save_cli_profile(
    federee: str,
    tenant_name: str,
    ssh_private_key_path_to_save: str,
    ssh_public_key_path_to_save: str,
    profile: Optional[str] = None,
    token: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    region: Optional[str] = None,
    profiles_file_path: Path = ewc_hub_config.EWC_CLI_PROFILES_PATH,
) -> None:
    """
    Save all profile data (config + credentials) into a single profiles file.

    Parameters
    ----------
    federee : str
        Federee name.
    tenant_name : str
        Tenant name.
    ssh_private_key_path_to_save: str
        SSH private key path
    ssh_public_key_path_to_save: str
        SSH public key path
    profile : str, optional
        Explicit profile name. If None, auto-generated using federee-tenant.
    token : str, optional
        Authentication token.
    application_credential_id : str, optional
        Application credential ID.
    application_credential_secret : str, optional
        Application credential secret.
    region : str, optional
        Region for the profile.
    """
    resolved_profile = _resolve_profile(profile, federee, tenant_name)
    cfg = ConfigParser()
    cfg.read(profiles_file_path)

    # Fail if profile exists
    if resolved_profile in cfg:
        click.secho(
            f"❌ Profile '{resolved_profile}' already exists in {profiles_file_path}",
            fg="red",
            bold=True,
        )
        click.secho(
            "Use a different profile name or delete the existing profile first.",
            fg="yellow",
        )
        raise click.Abort()

    # --- Save profile data
    cfg[resolved_profile] = {}

    # Non-sensitive
    cfg[resolved_profile]["federee"] = federee
    cfg[resolved_profile]["tenant_name"] = tenant_name
    cfg[resolved_profile]["ssh_public_key_path"] = ssh_public_key_path_to_save
    cfg[resolved_profile]["ssh_private_key_path"] = ssh_private_key_path_to_save

    if region:
        cfg[resolved_profile]["region"] = region

    # Sensitive
    if token:
        cfg[resolved_profile]["token"] = token

    if application_credential_id:
        cfg[resolved_profile]["application_credential_id"] = application_credential_id

    if application_credential_secret:
        cfg[resolved_profile][
            "application_credential_secret"
        ] = application_credential_secret

    os.makedirs(os.path.dirname(profiles_file_path), exist_ok=True)
    with open(profiles_file_path, "w") as f:
        cfg.write(f)


def load_cli_profile(
    profile: Optional[str] = None,
    federee: Optional[str] = None,
    tenant_name: Optional[str] = None,
    profiles_file_path: Path = ewc_hub_config.EWC_CLI_PROFILES_PATH,
) -> Dict[str, Optional[str]]:
    """
    Load all profile data (config + credentials) from the single profiles file.

    Parameters
    ----------
    profile : str, optional
        Explicit profile name to load. If None, auto-resolved from federee and tenant_name.
    federee : str, optional
        Federee name, used for auto-resolution if profile is None.
    tenant_name : str, optional
        Tenant name, used for auto-resolution if profile is None.
    profiles_file_path : Path, default to ewc_hub_config.EWC_CLI_PROFILES_PATH
        The path to the file with all profiles.

    Returns
    -------
    dict
        Combined profile data.

    Raises
    ------
    click.Abort
        If the profile cannot be found or cannot be resolved.
    """
    if profile is None:
        if not federee or not tenant_name:
            click.secho(
                "❌ Either 'profile' must be provided or both 'federee' and 'tenant_name'.",
                fg="red",
                bold=True,
            )
            raise click.Abort()
        profile = _resolve_profile(profile, federee, tenant_name)

    cfg = ConfigParser()
    cfg.read(profiles_file_path)

    # Case 1: file missing or empty
    if not os.path.exists(profiles_file_path) or not cfg.sections():
        click.secho(
            "❌ No profiles found.",
            fg="red",
            bold=True,
        )
        click.secho(
            f"Searched in: {profiles_file_path}",
            fg="cyan",
        )
        click.secho(
            "Please run 'ewc login' first to create a profile.",
            fg="yellow",
        )
        raise click.Abort()

    default_profile = ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME
    # Case 2: requested profile missing
    if profile and profile not in cfg:
        if profile != default_profile:
            click.secho(
                f"❌ Profile '{profile}' not found.",
                fg="red",
                bold=True,
            )
            click.secho(
                f"Searched in: {profiles_file_path}",
                fg="cyan",
            )
            if cfg.sections():
                click.secho(
                    f"ℹ️ The {profile} profile does not exist, but other profiles are available:",
                    fg="yellow",
                )
                for name in cfg.sections():
                    click.secho(f"  • {name}", fg="green")

                click.secho(
                    "You can either:",
                    fg="yellow",
                )
                if default_profile in cfg:
                    click.secho(
                        "  • Use the default without --profile",
                        fg="cyan",
                    )
                click.secho(
                    "  • Use one of the existing profiles with --profile <profile_name>",
                    fg="cyan",
                )
                click.secho(
                    "  • Or run 'ewc login' to create a new profile",
                    fg="cyan",
                )

        # Case 3: default profile missing but others exist
        if profile == default_profile and default_profile not in cfg and cfg.sections():
            click.secho(
                "ℹ️ The default profile does not exist, but other profiles are available:",
                fg="yellow",
            )
            for name in cfg.sections():
                click.secho(f"  • {name}", fg="green")

            click.secho(
                "You can either:",
                fg="yellow",
            )
            click.secho(
                "  • Use one of the existing profiles with --profile <profile_name>",
                fg="cyan",
            )
            click.secho(
                "  • Or run 'ewc login' to create the default profile automatically",
                fg="cyan",
            )

        raise click.Abort()

    section = cfg[profile]

    federee = section.get("federee")

    allowed_federees = [f for f in ewc_hub_config.EWC_CLI_SITE_MAP]
    if federee not in allowed_federees:
        raise ClickException(
            f"`{federee}` federee not supported. Check your profiles in ~/.ewccli/profiles. Please use one from the following: {allowed_federees}"
        )

    # Check if SSH keys path exist
    ssh_public_key_path = section.get("ssh_public_key_path")

    if not ssh_public_key_path:
        raise ClickException(
            f"`ssh_public_key_path` key is missing from your profile {profile}, please rerun ewc login."
        )
        
    ssh_private_key_path = section.get("ssh_private_key_path")

    if not ssh_private_key_path:
        raise ClickException(
            f"`ssh_private_key_path` key is missing from your profile {profile}, please rerun ewc login."
        )


    return {
        "profile": profile,
        "federee": federee,
        "tenant_name": section.get("tenant_name"),
        "ssh_public_key_path": ssh_public_key_path,
        "ssh_private_key_path": ssh_private_key_path,
        "region": section.get("region"),
        "token": section.get("token"),
        "application_credential_id": section.get("application_credential_id"),
        "application_credential_secret": section.get("application_credential_secret"),
    }


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


def ssh_keys_match(ssh_private_key_path: str, ssh_public_key_path: str) -> bool:
    """
    Check whether an SSH private key corresponds to a given public key.

    Supports PEM and OpenSSH private key formats and common SSH algorithms
    such as RSA, ECDSA, and Ed25519.

    Args:
        ssh_private_key_path: Path to the SSH private key file.
        ssh_public_key_path: Path to the SSH public key file (.pub).

    Returns:
        True if the public key matches the private key.

    Raises:
        ValueError: If the private key format or algorithm is unsupported.
    """
    # Ensure files exist
    for p in [ssh_private_key_path, ssh_public_key_path]:
        if not Path(p).expanduser().is_file():
            raise ValueError(f"SSH key file does not exist: {p}")

    with open(ssh_private_key_path, "rb") as f:
        private_data = f.read()

    private_key = None

    try:
        private_key = serialization.load_pem_private_key(private_data, password=None)
    except ValueError:
        try:
            private_key = serialization.load_ssh_private_key(private_data, password=None)
        except ValueError:
            raise ValueError("Unsupported or invalid private key format")

    derived_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )

    # Read provided public key and strip comment
    with open(ssh_public_key_path, "r") as f:
        parts = f.read().strip().split()
        if len(parts) < 2:
            raise ValueError(f"Invalid public key format: {ssh_public_key_path}")
        provided_public = " ".join(parts[:2]).encode()

    return derived_public == provided_public


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
    resolved_profile: str
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
    Path(ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH).parent.mkdir(parents=True, exist_ok=True)

    ssh_private_key_path = ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH / f"{resolved_profile}_id_rsa"
    # Save private key
    with open(ssh_private_key_path, "wb") as f:
        f.write(private_key_pem)

    # Restrict permissions to owner only
    os.chmod(ssh_private_key_path, 0o600)

    ssh_public_key_path = ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH / f"{resolved_profile}_id_rsa.pub"
    # Save public key
    with open(ssh_public_key_path, "wb") as f:
        f.write(public_key_ssh)

    # Public key can be world-readable
    os.chmod(ssh_public_key_path, 0o644)

    _LOGGER.info(
        f"SSH key pair generated at {ssh_private_key_path} and {ssh_public_key_path}"
    )

    return ssh_private_key_path, ssh_public_key_path
