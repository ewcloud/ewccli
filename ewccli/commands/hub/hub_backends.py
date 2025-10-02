#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Hub: EWC Hub interaction items specific methods."""

import os
import shutil
import sys
import json
import time
from pathlib import Path
from typing import Tuple, Optional

import requests
from openstack import connection

from ewccli.utils import run_command_from_host
from ewccli.enums import Federee
from ewccli.backends.ansible.backend_ansible import AnsibleBackend
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)

ansible_backend = AnsibleBackend()

HUB_ENV_VARIABLES_MAP = {
    "password_allowed_ip_ranges": {
        Federee.ECMWF.value: ["192.168.1.0/24"],
        Federee.EUMETSAT.value: ["10.0.0.0/24"],
    },
    "whitelisted_ip_ranges": {
        Federee.ECMWF.value: ["192.168.1.0/24"],
        Federee.EUMETSAT.value: ["10.0.0.0/24"],
    },
    "os_network_name": {
        Federee.ECMWF.value: None,
        Federee.EUMETSAT.value: "private"
    },
    "os_subnet_name": {
        Federee.ECMWF.value: None,
        Federee.EUMETSAT.value: "private-subnet",
    },
    "os_subnet_cidr": {
        Federee.ECMWF.value: "192.168.1.0/24",
        Federee.EUMETSAT.value: "10.0.0.0/24",
    },
}


def get_hub_item_env_variable_value(
    hub_item_env_variables_map: dict,
    federee: str,
    variable_name: str,
    openstack_api: Optional[connection.Connection] = None,
) -> str:
    """
    Retrieve the value of a HUB_ENV_VARIABLES_MAP variable for a given federee.

    If the value is a string or list defined in HUB_ENV_VARIABLES_MAP, return it directly.
    If the value must be determined dynamically from the OpenStack client, query it.

    Args:
        hub_item_env_variables_map
        openstack_api: An authenticated OpenStack SDK client.
        federee (str): The federee key (e.g., Federee.ECMWF.value, Federee.EUMETSAT.value).
        variable_name (str): The variable name to retrieve from HUB_ENV_VARIABLES_MAP.

    Returns:
        Any: The resolved value (string, list, etc.).

    Raises:
        KeyError: If the variable or federee entry does not exist.
        ValueError: If dynamic lookup fails.
    """
    os_network_name = "private"
    os_subnetwork_name = "private-subnet"

    # --- Handle dynamic lookups ---
    if variable_name == "os_network_name" and federee == Federee.ECMWF.value:
        if openstack_api:
            networks = list(openstack_api.network.networks())
            for net in networks:
                if "private" in net.name.lower():
                    os_network_name = net.name
            raise ValueError("No network containing 'private' found.")

    hub_item_env_variables_map["os_network_name"] = {
        Federee.ECMWF.value: os_network_name,
        Federee.EUMETSAT.value: "private",
    }

    if variable_name == "os_subnet_name" and federee == Federee.ECMWF.value:
        if openstack_api:
            networks = list(openstack_api.network.networks())
            for net in networks:
                if "private" in net.name.lower():
                    subnets = list(openstack_api.network.subnets(network_id=net.id))
                    if subnets:
                        os_subnetwork_name = subnets[0].name
            raise ValueError("No subnet found for network containing 'private'.")

    hub_item_env_variables_map["os_subnet_name"] = {
        Federee.ECMWF.value: os_subnetwork_name,
        Federee.EUMETSAT.value: "private-subnet",
    }

    # If not dynamic, return directly
    return hub_item_env_variables_map[variable_name][federee]


def check_github_repo_accessible(source: str) -> bool:
    """
    Check if a GitHub repository exists and is publicly accessible.

    Args:
        source (str): The full URL of the GitHub repository.

    Returns:
        bool: True if the repository is accessible, False otherwise.
    """
    # Remove trailing .git if present
    if source.endswith(".git"):
        source = source[:-4]

    # Normalize trailing slash
    source = source.rstrip("/")

    # Build API URL
    api_url = source.replace(
        "https://github.com/", "https://api.github.com/repos/"
    )

    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            _LOGGER.info(f"✅ Repository is accessible: [blue]{source}[/blue]")
            return True
        elif response.status_code == 404:
            _LOGGER.error(f"❌ Repository not found: [red]{source}[/red]")
        else:
            _LOGGER.error(
                f"⚠️ Unexpected response ({response.status_code}) when checking: {source}"
            )
    except requests.RequestException as e:
        _LOGGER.error(f"🚨 Network error while accessing repository: {e}")

    return False


def git_clone_item(
    source: str,
    repo_name: str,
    command_path: str,
    dry_run: bool = False,
    force: bool = False,
):
    """Git clone item."""
    ########################################################################
    # Prepare input for items
    ########################################################################
    _LOGGER.info("Preparing item...")
    ########################################################################
    # Git clone item to the correct path
    ########################################################################

    # Define the directory path for outputs
    dir_path = Path(command_path)

    # Create the directory if it doesn't exist
    dir_path.mkdir(parents=True, exist_ok=True)

    # main_file_name = os.path.basename(source)

    repo_path = Path(f"{command_path}/{repo_name}")
    # file_name_path = Path(f"{repo_path}/{main_file_name}")

    if force:
        # Delete the folder and all its contents
        shutil.rmtree(repo_path)

    if not check_github_repo_accessible(source):
        _LOGGER.error("The repository is not accessible or does not exist.")
        sys.exit(1)

    if repo_path.exists() and not force:
        return (
            0,
            f"📁 Main Repository {repo_name} already exists at {command_path}. Skipping git clone.",
        )

    _LOGGER.info(
        f"⬇️ Starting to clone the repository '{repo_name}' into {command_path}..."
    )
    git_command = [
        f"""[ -d "$(basename '{source}' .git)/.git" ] || git clone '{source}' """
    ]
    # Get Git Repository URL
    return_code, message = run_command_from_host(
        description="git clone repository",
        command=git_command,
        cwd=command_path,
        dry_run=dry_run,
    )
    return return_code, message


def run_ansible_item(
    item: str,
    item_inputs: Optional[dict],
    server_name: str,
    ip_machine: str,
    username: str,
    repo_name: str,
    main_file_path: str,
    requirements_file_relative_path: str,
    cwd_command: str,
    ssh_private_key_path: str,
    dry_run: bool = False,
):
    """Run item based on Ansible Playbook."""
    if dry_run:
        return 0, "Dry run. No actions"

    requirements_file_path = f"{cwd_command}/{repo_name}/{requirements_file_relative_path}"
    # Install roles
    ansible_backend.install_ansible_roles(
        requirements_path=requirements_file_path, dry_run=dry_run
    )

    # Create inventory file
    if not ip_machine:
        machine_ips = [""]
    else:
        machine_ips = [ip_machine]

    hosts_file_name = f"hosts-{item}.ini"
    hosts_file_path = f"{cwd_command}/{repo_name}/{hosts_file_name}"
    _LOGGER.debug(f"Saving {hosts_file_name} file to {hosts_file_path}")

    inventory_content = f"[{server_name}]\n"
    inventory_content += "\n".join(machine_ips) + "\n\n"

    _LOGGER.debug(f"Inventory content {inventory_content}")

    with open(hosts_file_path, "w") as f:
        f.write(inventory_content)

    # ansible_command = [
    #     f"ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i {hosts_file_path} -u {username}"
    #     f" --private-key {ssh_private_key_path} {main_file_path}"
    # ]
    # return_code = ansible_backend.run_ansible(
    #     description="run ansible",
    #     command=ansible_command,
    #     cwd=f"{cwd_command}/{repo_name}",
    #     dry_run=dry_run
    # )

    env = {
        # "ANSIBLE_PRIVATE_KEY_FILE": ssh_private_key_path,
        "ANSIBLE_HOST_KEY_CHECKING": "False",  # Optional, disables host key prompt,
        "ANSIBLE_PORT": "2222",  # <- Set SSH port globally
        "ANSIBLE_PYTHON_INTERPRETER": "/usr/bin/python3",
        # "ANSIBLE_SSH_ARGS": "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no",
    }

    ansible_command = [
        f"ansible-playbook -i {hosts_file_path} -u {username}"
        f" --private-key {ssh_private_key_path} {main_file_path}"
    ]

    _LOGGER.info(f"Deploying Ansible Playbook item {item}...")
    _LOGGER.info("⏳ This could take a few minutes, grab another beverage meanwhile...")
    time.sleep(15)
    if item_inputs:
        extra_vars = json.dumps(item_inputs)
    else:
        extra_vars = ""

    max_attempts = 5
    delay_seconds = 10  # wait between attempts

    for attempt in range(1, max_attempts + 1):
        _LOGGER.info(f"Running attempt {attempt}/{max_attempts}...")

        return_code = ansible_backend.run_ansible_live(
            working_directory_path=f"{cwd_command}/{repo_name}",
            description=ansible_command[0],
            host=server_name,
            cmdline=[
                "ansible-playbook",
                "-i",
                hosts_file_path,
                "-u",
                username,
                "--private-key",
                ssh_private_key_path,
                main_file_path,
            ],
            extra_vars=extra_vars,
            env=env,
        )

        if return_code == 0:
            # Success
            _LOGGER.info(f"Attempt {attempt}/{max_attempts} succeeded.")
            return return_code
        else:
            _LOGGER.warning(f"Attempt {attempt}/{max_attempts} failed")
            if attempt < max_attempts:
                _LOGGER.info(f"Retrying in {delay_seconds} seconds...")
                time.sleep(delay_seconds)
            else:
                _LOGGER.error(f"All attempts failed. EWC CLI could not install {item} Ansible Playbook item.")
                return_code = 1

    return return_code


def run_post_ansible_operations(
    item: str,
    command_path: str,
    repo_name: str,
    server_name: str,
    internal_ip_machine: str,
):
    """Run post ansible operation if something goes wrong."""
    hosts_file_name = f"hosts-{item}.ini"
    hosts_file_path = f"{command_path}/{repo_name}/{hosts_file_name}"

    inventory_content = f"[{server_name}]\n"
    inventory_content += "\n".join([internal_ip_machine]) + "\n\n"

    _LOGGER.debug(f"Post run inventory content {inventory_content}")

    with open(hosts_file_path, "w") as f:
        f.write(inventory_content)


def run_ansible_playbook_item(
    item: str,
    server_name: str,
    username: str,
    repo_name: str,
    main_file_path: str,
    requirements_file_relative_path: str,
    command_path: str,
    ip_machine: str,
    ssh_private_key_path: str,
    item_inputs: Optional[dict],
    dry_run: bool = False,
) -> Tuple[int, str]:
    """Deploy Ansible item."""
    ansible_return_code = run_ansible_item(
        item=item,
        item_inputs=item_inputs,
        server_name=server_name,
        ip_machine=ip_machine,
        username=username,
        repo_name=repo_name,
        main_file_path=main_file_path,
        requirements_file_relative_path=requirements_file_relative_path,
        cwd_command=command_path,
        ssh_private_key_path=ssh_private_key_path,
        dry_run=dry_run,
    )

    if ansible_return_code != 0:
        return ansible_return_code, "⚠️ Ansible execution failed. Check errors above."

    return 0, "Ansible run successfully"
