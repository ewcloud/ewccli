#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Utils."""

import subprocess
import secrets
import string
from datetime import datetime, timezone
from typing import Optional, Tuple, List

import requests

from ewccli.configuration import config as ewc_hub_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


def generate_random_id(length: int = 10) -> str:
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
    env: Optional[dict[str, str]] = None,
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


def download_items(force: bool = False) -> None:
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
        return
    except requests.Timeout:
        _LOGGER.error("⚠️ Request timed out.")
    except requests.RequestException as e:
        _LOGGER.error(f"❌ Failed to download file: {e}")
