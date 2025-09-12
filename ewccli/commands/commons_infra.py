#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Common methods for commands using infrastructure."""

import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Dict

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from click import ClickException
from openstack import connection

from ewccli.utils import save_ssh_keys
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.enums import Federee
from ewccli.configuration import config as ewc_hub_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)
_EWC_CLI_SLEEP_TIME = 30  # seconds

console = Console()


def check_server_conflict_with_inputs(
    server_info: dict,
    server_info_image: Optional[str] = None,
    image_name: Optional[str] = None,
    keypair_name: Optional[str] = None,
    flavour_name: Optional[str] = None,
    networks: Optional[tuple] = None,
    security_groups: Optional[tuple] = None,
):
    """Check if user-provided values conflict with an existing server."""
    if not server_info:
        return  # Server does not exist yet

    diffs = []

    def compare(field, provided, actual):
        actual_str = str(actual)

        if provided is None:
            return

        if isinstance(provided, list):
            # Check if actual is in the list (as string comparison)
            if actual_str not in map(str, provided):
                diffs.append((field, actual_str, ", ".join(map(str, provided))))
        else:
            # Direct value comparison
            if actual_str != str(provided):
                diffs.append((field, actual_str, str(provided)))

    def _get_network_names(server_info):
        if server_info.addresses:
            return ", ".join(server_info.addresses.keys())
        return ""

    def _get_security_groups_string(server_info):
        groups = getattr(server_info, "security_groups", [])
        return ",".join(sg.get("name") for sg in groups)

    if image_name and server_info_image:
        compare("Image", image_name, server_info_image)

    if keypair_name:
        compare("Keypair", keypair_name, getattr(server_info, "key_name", None))

    if flavour_name:
        compare(
            "Flavour",
            flavour_name,
            getattr(server_info.get("flavor", {}), "original_name", None),
        )

    # To be checked yet.
    if networks:
        compare("Network", ",".join(networks), _get_network_names(server_info))

    if security_groups:
        compare(
            "Security Groups",
            ",".join(security_groups),
            _get_security_groups_string(server_info),
        )

    return diffs


def show_server_input_requested_summary(
    security_groups: tuple,
    networks: tuple,
    image_name: Optional[str] = None,
    flavour_name: Optional[str] = None,
    keypair_name: Optional[str] = None,
):
    """Print table with inputs for the server."""
    table = Table(
        title="🧾 Server Configuration Inputs Summary", title_style="bold green"
    )

    table.add_column("Parameter", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Image", image_name)
    table.add_row("Flavour", flavour_name)
    table.add_row("Network", ", ".join(networks))
    table.add_row("Security Groups", ", ".join(security_groups))
    table.add_row("Keypair", keypair_name)

    console.print(table)


def show_server_inputs_difference_table(server_name: str, diffs: dict):
    """Show table of inputs with differences requested."""
    if not diffs:
        return False

    table = Table(
        title="❌ Configuration mismatch with existing server",
        show_lines=True,
    )
    table.add_column("Parameter", style="bold cyan")
    table.add_column("Existing Value", style="bold yellow")
    table.add_column("Requested Value", style="bold green")

    for param, existing, requested in diffs:
        table.add_row(param, existing, requested)

    console.print(table)

    raise ClickException(
        f"The server '{server_name}' already exists with different configuration."
        " Use a different --server-name or use --force to redeploy."
    )


def check_ssh_keys_exist(ssh_public_key_path: Path, ssh_private_key_path: Path) -> None:
    """
    Verifies the existence of the specified SSH key files.

    If either the private or public key file does not exist at the given paths,
    raises a FileNotFoundError with detailed instructions for resolution.

    Parameters:
        ssh_private_key_path (Path): Path to the private SSH key file.
        ssh_public_key_path (Path): Path to the public SSH key file.

    Raises:
        FileNotFoundError: If one or both SSH key files are missing.

    Environment Variables:
        EWC_CLI_SSH_PRIVATE_KEY_PATH - optional custom path for the private SSH key.
        EWC_CLI_SSH_PUBLIC_KEY_PATH  - optional custom path for the public SSH key.

    Example:
        >>> check_ssh_keys_exist(Path("~/.ssh/id_rsa"), Path("~/.ssh/id_rsa.pub"))
    """
    missing_msgs = []

    if not ssh_private_key_path.is_file():
        missing_msgs.append(
            f"🔒 [bold red]Missing Private Key:[/bold red] {ssh_private_key_path}"
        )
    if not ssh_public_key_path.is_file():
        missing_msgs.append(
            f"🔓 [bold red]Missing Public Key:[/bold red] {ssh_public_key_path}"
        )

    if missing_msgs:
        panel_content = (
            "\n".join(missing_msgs)
            + "\n\n"
            + "[bold yellow]Tip:[/bold yellow] You can run ewc login and create them.\n"
            + "[bold yellow]Tip:[/bold yellow] You can specify custom paths with:\n"
            + '[green]export EWC_CLI_SSH_PRIVATE_KEY_PATH="/path/to/id_rsa"[/green]\n'
            + '[green]export EWC_CLI_SSH_PUBLIC_KEY_PATH="/path/to/id_rsa.pub"[/green]'
        )

        console.print(
            Panel(
                panel_content, title="SSH Key Check Failed", style="red", expand=False
            )
        )
        sys.exit(1)


def resolve_image_and_flavor(
    federee: str,
    flavour_name: Optional[str] = None,
    image_name: Optional[str] = None,
    is_gpu: bool = False,
) -> Tuple[int, str, Dict[str, str]]:
    """
    Resolve both the image and flavor for the given federee.

    Args:
        federee (str): Target federee ewccli.enums.Federee.
        flavour_name (Optional[str]): Name of the desired flavor.
        image_name (Optional[str]): Name of the desired OS image.
        is_gpu (bool): Whether a GPU-enabled flavor is required.

    Returns:
        Tuple[int, str, Optional[Dict[str, str]]]:
            - status_code: 0 for success, 1 for error
            - message: success or error message
            - result: dict containing 'image_name', 'flavour_name', 'username' on success, None on error
    """
    result: Dict[str, str] = {}

    try:
        if is_gpu:
            _LOGGER.info("The selected item requires a GPU flavor...")
            image_name = ewc_hub_config.DEFAULT_IMAGES_GPU_MAP.get(federee)

            if not flavour_name:
                flavour_name = ewc_hub_config.DEFAULT_GPU_FLAVOURS_MAP.get(federee)
            else:
                gpu_flavours = ewc_hub_config.GPU_FLAVOURS_MAP.get(federee, [])

                if flavour_name not in gpu_flavours:
                    gpu_list = ", ".join(gpu_flavours)
                    message = (
                        "[bold red]❌ Invalid flavour:[/bold red] The selected flavour does not support GPUs.\n"
                        f"[bold green]✔️ Available GPU flavours:[/bold green] {gpu_list}"
                    )
                    return 1, message, result
        else:
            if not image_name:
                image_name = ewc_hub_config.EWC_CLI_DEFAULT_IMAGE

            if not flavour_name:
                flavour_name = ewc_hub_config.DEFAULT_CPU_FLAVOURS_MAP.get(federee)

        # Collect all valid images for this federee
        ewc_images: list = list(ewc_hub_config.EWC_CLI_IMAGES.values()) + [
            ewc_hub_config.DEFAULT_IMAGES_GPU_MAP.get(federee)
        ]

        if image_name not in ewc_images:
            message = (
                "❌ Unsupported image selected.\n"
                "🖥️ EWC currently supports the following operating system images:\n"
                f"👉 [bold green]{', '.join(ewc_images)}[/bold green]\n"
                "➡️ Please choose one of the supported OS images."
            )
            return 1, message, result

        if not image_name or not flavour_name:
            return (
                1,
                f"One of image_name {image_name} or flavour_name {flavour_name} is missing or empty",
                result,
            )

        username = (
            ewc_hub_config.EWC_CLI_GPU_IMAGES_USER.get(federee)
            if is_gpu
            else ewc_hub_config.EWC_CLI_IMAGES_USER.get(image_name)
        )

        if not username:
            return 1, f"username {username} is missing or empty", result

        result = {
            "image_name": image_name,
            "flavour_name": flavour_name,
            "username": username,
        }
        return 0, "Success", result

    except Exception as e:
        return 1, f"Unexpected error: {str(e)}", result


def resolve_machine_ip(
    federee: str,
    server_info: dict,
) -> Tuple[int, str, Optional[Dict[str, Optional[str]]]]:
    """
    Resolve the internal and external IPs of a machine.

    Args:
        federee (str): Target federee (e.g., "EUMETSAT", "ECMWF").
        server_info (dict): Server information returned by the cloud API.

    Returns:
        Tuple[int, str, Optional[Dict[str, Optional[str]]]]:
            - status_code: 0 for success, 1 for error
            - message: success or error message
            - result: dict containing 'internal_ip', 'external_ip' on success, None on error
    """
    try:
        external_ip_machine = None
        internal_ip_machine = None
        addresses = server_info.get("addresses")

        if not addresses:
            message = "❌ Could not find networks for this machine."
            _LOGGER.error(message)
            return 1, message, None

        network_info = {}

        if federee == Federee.EUMETSAT.value:
            if "private" in addresses:
                for net in addresses.get("private"):
                    if net.get("OS-EXT-IPS:type"):
                        ip_type = net["OS-EXT-IPS:type"]
                        network_info[f"network-private-{ip_type}"] = net.get("addr")

            _LOGGER.debug(f"Networks for machine: {network_info}")

            external_ip_machine = network_info.get("network-private-floating")
            internal_ip_machine = network_info.get("network-private-fixed")

        elif federee == Federee.ECMWF.value:
            external_network = ewc_hub_config.DEFAULT_EXTERNAL_NETWORK_MAP[federee]

            for net_name, addr_list in addresses.items():
                if net_name.startswith("private-") and addr_list:
                    for addr in addr_list:
                        if str(addr["addr"]).startswith("136."):
                            external_ip_machine = addr["addr"]
                        else:
                            internal_ip_machine = addr["addr"]

                if net_name == ewc_hub_config.DEFAULT_EXTERNAL_NETWORK_MAP[federee]:
                    external_ip_machine = addresses[external_network][0]["addr"]

        _LOGGER.debug(
            f"external_ip_machine: {external_ip_machine}, internal_ip_machine: {internal_ip_machine}"
        )

        result = {
            "internal_ip_machine": internal_ip_machine,
            "external_ip_machine": external_ip_machine,
        }
        return 0, "Success", result

    except Exception as e:
        message = f"Unexpected error: {str(e)}"
        _LOGGER.error(message)
        return 1, message, None


def get_deployed_server_info(
    federee: str,
    server_info: dict,
    image_name: Optional[str] = None,
):
    """Get deployed server info."""
    _LOGGER.debug(server_info)
    vm_info = {}
    vm_info["id"] = server_info.get("id")
    vm_info["name"] = server_info.get("name")
    flavor = server_info.get("flavor")
    if flavor is not None:
        vm_info["flavor"] = flavor.get("original_name")
    else:
        vm_info["flavor"] = None
    vm_info["keypair"] = server_info.get("key_name")
    vm_info["status"] = server_info.get("status", "")

    vm_info["image"] = image_name

    addresses = server_info.get("addresses")

    identified_networks = {}

    if federee == Federee.EUMETSAT.value and addresses:
        if "private" in addresses:
            for net in addresses.get("private"):
                if net.get("OS-EXT-IPS:type"):
                    ip_type = net["OS-EXT-IPS:type"]
                    identified_networks[f"network-private-{ip_type}"] = net.get("addr")

        if "manila-network" in addresses:
            for net in addresses.get("manila-network"):
                identified_networks["sfs-manila-network"] = net.get("addr")

    if federee == Federee.ECMWF.value and addresses:
        for address, address_v in addresses.items():
            identified_networks[f"network-{address}"] = [
                v.get("addr") for v in address_v
            ]

    vm_info["networks"] = identified_networks

    vm_info["id"] = server_info.get("id", "")

    vm_info["security-groups"] = [
        s["name"] for s in server_info.get("security_groups") or []
    ]
    return vm_info


def list_server_details(
    vm_info: dict,
):
    """Print detailed info of a single server in a two-column table."""
    console = Console()

    table = Table(
        show_header=False,
        box=box.MINIMAL_DOUBLE_HEAD,
        title=f"Openstack Server: {vm_info.get('name')}",
    )

    table.add_column("Property", style="bold green", no_wrap=True)
    table.add_column("Value", style="white")

    # Add rows with all the info you want to show
    table.add_row("Name", str(vm_info.get("name")))
    table.add_row("Status", str(vm_info.get("status")))
    table.add_row("Flavor", str(vm_info.get("flavor")))
    table.add_row("Image", str(vm_info.get("image")))
    networks = []
    retrieved_networks = vm_info.get("networks") or {}
    for n_name, n_value in retrieved_networks.items():
        if isinstance(n_value, list):
            networks.append(f"{n_name} ({', '.join(n_value)})")
        else:
            networks.append(f"{n_name} ({n_value})")

    table.add_row("Networks", "\n".join(networks))
    table.add_row("Security Groups", ",".join(vm_info.get("security-groups") or []))
    table.add_row("ID", str(vm_info.get("id", "")))

    console.print(table)


def deploy_server(
    openstack_backend: OpenstackBackend,
    openstack_api: connection.Connection,
    federee: str,
    server_inputs: dict,
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    ssh_private_encoded: Optional[str] = None,
    ssh_public_encoded: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
):
    """Deploy Server in Openstack."""
    outputs: dict[str, Optional[str]] = {}

    if dry_run:
        return 0, "dru run enabled.", outputs

    server_name: str = server_inputs["server_name"]
    keypair_name: str = server_inputs["keypair_name"]
    is_gpu: bool = server_inputs["is_gpu"]
    image_name: Optional[str] = server_inputs["image_name"]
    flavour_name: Optional[str] = server_inputs["flavour_name"]
    external_ip: bool = server_inputs["external_ip"]
    networks: Optional[tuple] = server_inputs["networks"]
    security_groups: Optional[tuple] = server_inputs["security_groups"]

    _LOGGER.info(f"Preparing to deploy server {server_name}...")

    save_ssh_keys(ssh_public_encoded, ssh_private_encoded)

    check_ssh_keys_exist(
        ssh_public_key_path=Path(ssh_public_key_path),
        ssh_private_key_path=Path(ssh_private_key_path),
    )

    try:
        is_valid, message = openstack_backend.check_server_inputs(
            conn=openstack_api,
            image_name=image_name,
            flavour_name=flavour_name,
            networks=networks,
            security_groups=security_groups,
        )

        if not is_valid:
            return (
                1,
                f"Server creation inputs are not valid: {message}. Please check the input parameters and try again.",
                outputs,
            )
    except Exception as e:
        return 1, f"Could not check inputs from Openstack due to {e}", outputs

    if not force:
        # Retrive machine if exists
        try:
            existing_server_info = openstack_api.get_server(name_or_id=server_name)
        except Exception as e:
            return (
                1,
                f"Failed to retrieve information for server {server_name} due to {e}",
                outputs,
            )

        if existing_server_info:
            if not (
                existing_server_info.metadata.get("deployed")
                and existing_server_info.metadata.get("deployed") == "ewccli"
            ):
                return (
                    1,
                    f"Server {server_name} already exists and it has not been deployed with the EWC CLI. Exiting.",
                    outputs,
                )

            try:
                # Fetch image name from the image ID
                image = openstack_api.compute.find_image(
                    getattr(existing_server_info.image, "id", None)
                )
                server_info_image = image.name if image else None
            except Exception as e:
                return (
                    1,
                    f"Could not retrieve image name of {server_name} due to {e}",
                    outputs,
                )

            diffs = check_server_conflict_with_inputs(
                server_info=existing_server_info,
                server_info_image=server_info_image,
                image_name=image_name,
                keypair_name=keypair_name,
                flavour_name=flavour_name,
                networks=networks,
                security_groups=security_groups,
            )
            if diffs:
                show_server_inputs_difference_table(
                    server_name=server_name, diffs=diffs
                )

    ##################################################################################
    # Flavour and Image
    ##################################################################################
    sc, resolve_message, resolved_info = resolve_image_and_flavor(
        federee=federee, flavour_name=flavour_name, image_name=image_name, is_gpu=is_gpu
    )
    if sc != 0 or not resolved_info:
        return 1, resolve_message, outputs

    resolved_image_name: str = resolved_info["image_name"]
    resolved_flavour_name: str = resolved_info["flavour_name"]
    username: str = resolved_info["username"]

    ##################################################################################
    # Network (private) and security groups
    ##################################################################################
    if not networks:
        default_network = ewc_hub_config.DEFAULT_NETWORK_MAP.get(federee)
        if federee == Federee.ECMWF.value:
            networks_identified = [n.name for n in openstack_api.list_networks()]
            networks = tuple([n for n in networks_identified if default_network in n])
        else:
            networks = tuple([default_network])

    security_groups = security_groups or ewc_hub_config.DEFAULT_SECURITY_GROUP_MAP.get(federee)

    # if "default" not in security_groups:
    #     security_groups += ("default",)

    show_server_input_requested_summary(
        image_name=resolved_image_name,
        flavour_name=resolved_flavour_name,
        networks=networks,
        security_groups=security_groups,
        keypair_name=keypair_name,
    )

    #################################################################################
    # Get or Create keypair
    #################################################################################
    key_pair_message = ""

    if force:
        _LOGGER.info("Force enabled, keypair will be deleted first if existing.")
        keypair_status, key_pair_message = openstack_backend.delete_keypair(
            conn=openstack_api, keypair_name=keypair_name
        )
        if not keypair_status[0]:
            return 1, message, outputs

    keypair_status, key_pair_message = openstack_backend.create_keypair(
        conn=openstack_api,
        keypair_name=keypair_name,
        public_key_path=Path(ssh_public_key_path),
    )

    if not keypair_status[0]:
        return 1, key_pair_message, outputs
    else:
        _LOGGER.info(key_pair_message)

    #################################################################################
    # Get or Create Server
    #################################################################################
    if force:
        _LOGGER.warning("Force enabled, server will be deleted first, if existing.")

        openstack_server_status, delete_server_message = (
            openstack_backend.delete_server(conn=openstack_api, server_name=server_name)
        )
        if not openstack_server_status[0]:
            return 1, delete_server_message, outputs
        else:
            _LOGGER.info(delete_server_message)

        time.sleep(_EWC_CLI_SLEEP_TIME)

    _LOGGER.info("Preparing to deploy VM on Openstack...")

    if not resolved_image_name or not resolved_flavour_name or not username:
        return (
            1,
            f"One of image_name {resolved_image_name}, flavour_name {resolved_flavour_name}, or username {username} is missing or empty",
            outputs,
        )

    openstack_server_status, create_server_message, server_info = (
        openstack_backend.create_server(
            conn=openstack_api,
            server_name=server_name,
            image_name=resolved_image_name,
            flavour_name=resolved_flavour_name,
            networks=networks,
            sec_groups=security_groups,
            keypair_name=keypair_name,
        )
    )

    if not openstack_server_status[0]:
        return 1, create_server_message, outputs
    else:
        _LOGGER.info(create_server_message)

    # Extract image ID (usually a dict with id field)
    server_info_image = server_info.get("image")

    image_id = (
        server_info_image.get("id")
        if isinstance(server_info_image, dict)
        else server_info_image.id
    )

    try:
        # Fetch image name from the image ID
        image = openstack_api.compute.find_image(image_id)
        image_name_used = image.name if image else "Unknown"
    except Exception as e:
        return 1, f"Could not retrieve image due to {e}", outputs

    vm_info = get_deployed_server_info(
        federee=federee,
        server_info=server_info,
        image_name=image_name_used,
    )

    list_server_details(vm_info)

    sc_resolve_ip, resolve_ip_message, resolve_ip_outputs = resolve_machine_ip(
        federee=federee, server_info=server_info
    )

    if external_ip and not resolve_ip_outputs.get("external_ip_machine"):
        openstack_floatingip_status, message, _ = openstack_backend.add_external_ip(
            conn=openstack_api, server=server_info, federee=federee
        )
        time.sleep(_EWC_CLI_SLEEP_TIME - 15)

        if not openstack_floatingip_status[0]:
            return 1, message, outputs
        else:
            _LOGGER.info(message)

    server_info = openstack_api.get_server(name_or_id=server_name)

    sc_resolve_ip, resolve_ip_message, resolve_ip_outputs = resolve_machine_ip(
        federee=federee, server_info=server_info
    )
    if sc_resolve_ip != 0:
        return 1, resolve_ip_message, outputs

    # make sure it's not None
    if resolve_ip_outputs is None:
        return 1, "No IPs identified.", outputs

    internal_ip_machine = resolve_ip_outputs["internal_ip_machine"]
    # enforce internal must not be empty
    if not internal_ip_machine:
        return (
            1,
            f"internal_ip_machine {internal_ip_machine} is missing or empty",
            outputs,
        )

    external_ip_machine = resolve_ip_outputs.get("external_ip_machine", None)

    outputs = {
        "internal_ip_machine": internal_ip_machine,
        "external_ip_machine": external_ip_machine,
        "server_info": server_info,
        "username": username,
    }

    return 0, "Server deployed successfully", outputs
