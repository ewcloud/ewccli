#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""EWC CLI: VM interaction."""

from __future__ import annotations

import sys
import os
from typing import Optional

from typing import Tuple, Dict, Any
from pydantic import BaseModel

import rich_click as click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from click import ClickException

from ewccli.configuration import config as ewc_hub_config
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.commands.commons import openstack_options
from ewccli.commands.commons import ssh_options
from ewccli.commands.commons import ssh_options_encoded
from ewccli.commands.commons import openstack_optional_options
from ewccli.commands.commons import CommonBackendContext
from ewccli.commands.commons import login_options
from ewccli.commands.commons_infra import check_user_ssh_keys
from ewccli.commands.commons_infra import get_deployed_server_info, list_server_details
from ewccli.commands.commons_infra import create_server_command
from ewccli.profile import ProfileStore
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)

console = Console()

infra_context = click.make_pass_decorator(CommonBackendContext, ensure=True)


# Command Group
@click.group(name="infra")  # type: ignore[misc]
@infra_context  # type: ignore[misc]
@login_options
def ewc_infra_command(ctx: click.Context, profile: str) -> None:
    """EWC Infrastructure commands group."""
    store = ProfileStore()

    if profile:
        ctx.cli_profile = store.load(name=profile)
        _LOGGER.info(f"Using `{profile}` profile.")
    else:
        ctx.cli_profile = store.load(name=ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME)
        _LOGGER.info(f"Using `{ctx.cli_profile.profile}` profile.")

    federee = ctx.cli_profile.federee
    application_credential_id = ctx.cli_profile.application_credential_id
    application_credential_secret = ctx.cli_profile.application_credential_secret
    ctx.openstack_backend = OpenstackBackend(
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
        auth_url=ewc_hub_config.EWC_CLI_SITE_MAP.get(federee),
    )


def list_server_table(servers: Dict[str, Any]) -> None:
    """List servers in a table with columns Name, Status, and Networks."""
    console = Console()

    table = Table(
        show_header=True,
        header_style="bold green",
        title="Openstack Servers",
        box=box.MINIMAL_DOUBLE_HEAD,
    )

    # Add columns
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Status", style="magenta")
    table.add_column("Networks", style="yellow")

    # Add each server as a row
    for server_id, server_info in servers.items():
        name = str(server_info.get("name", ""))
        status = str(server_info.get("status", ""))
        networks = str(server_info.get("networks", ""))
        table.add_row(name, status, networks)

    console.print(table)


class ServerAuthConfig(BaseModel):  # type: ignore[misc]
    federee: Optional[str] = None
    auth_url: Optional[str] = None
    application_credential_id: Optional[str] = None
    application_credential_secret: Optional[str] = None


class ServerSSHConfig(BaseModel):  # type: ignore[misc]
    keypair_name: str
    ssh_public_key_path: Optional[str] = None
    ssh_private_key_path: Optional[str] = None
    ssh_private_encoded: Optional[str] = None
    ssh_public_encoded: Optional[str] = None


class ServerNetworkConfig(BaseModel):  # type: ignore[misc]
    external_ip: bool = False
    networks: Optional[Tuple[str, ...]] = None
    security_groups: Optional[Tuple[str, ...]] = None


class ServerCreateOptions(BaseModel):  # type: ignore[misc]
    image_name: Optional[str] = None
    flavour_name: Optional[str] = None
    dry_run: bool = False
    force: bool = False


@ewc_infra_command.command("create", help="Create server in Openstack.")  # type: ignore[misc]
@infra_context  # type: ignore[misc]
@ssh_options
@ssh_options_encoded
@openstack_options
@openstack_optional_options
@click.option(  # type: ignore[misc]
    "--dry-run",
    envvar="EWC_CLI_DRY_RUN",
    default=False,
    is_flag=True,
    help="Simulate deployment without running.",
)
@click.option(  # type: ignore[misc]
    "--force",
    envvar="EWC_CLI_FORCE",
    is_flag=True,
    default=False,
    help="Force item recreation operation.",
)
@click.argument("server_name")  # type: ignore[misc]
def create_cmd(  # noqa: CFQ001, CCR001
    ctx: click.Context,
    server_name: str,
    auth: ServerAuthConfig,
    ssh: ServerSSHConfig,
    net: ServerNetworkConfig,
    opts: ServerCreateOptions,
) -> None:
    """Show Server from Openstack."""
    if opts.dry_run:
        _LOGGER.info("Dry run enabled...")

    cli_profile = ctx.cli_profile
    federee = auth.federee or cli_profile["federee"]

    # Try to fill from CLI profile if not provided
    if not ssh.ssh_public_key_path:
        ssh_public_key_path = cli_profile.get("ssh_public_key_path")

    if not ssh.ssh_private_key_path:
        ssh_private_key_path = cli_profile.get("ssh_private_key_path")

    check_user_ssh_keys(
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
    )

    _LOGGER.info(f"The server will be deployed on {federee} side of the EWC.")

    #####################################################################################
    # Authenticate to Openstack
    #####################################################################################

    try:
        # Step 1: Authenticate and initialize the OpenStack connection
        openstack_api = ctx.openstack_backend.connect(
            auth_url=auth.auth_url,
            application_credential_id=auth.application_credential_id,
            application_credential_secret=auth.application_credential_secret,
        )
    except Exception as op_error:
        raise ClickException(
            f"Could not connect to Openstack due to the following error: {op_error}"
        )

    server_inputs = {
        "server_name": server_name,
        "is_gpu": None,
        "image_name": opts.image_name,
        "keypair_name": ssh.keypair_name,
        "flavour_name": opts.flavour_name,
        "external_ip": net.external_ip,
        "networks": net.networks,
        "security_groups": net.security_groups,
    }

    os_status_code, os_message, outputs = create_server_command(
        openstack_backend=ctx.openstack_backend,
        openstack_api=openstack_api,
        federee=federee,
        server_inputs=server_inputs,
        ssh_private_encoded=ssh.ssh_private_encoded,
        ssh_public_encoded=ssh.ssh_public_encoded,
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
        dry_run=opts.dry_run,
        force=opts.force,
    )

    internal_ip_machine = outputs["internal_ip_machine"]
    external_ip_machine = outputs["external_ip_machine"]
    normalized_image_name = outputs["normalized_image_name"]

    username: Optional[str] = ewc_hub_config.EWC_CLI_IMAGES_USER.get(
        normalized_image_name
    )

    # If missing the mapping in the configuration is missing, so configuration file needs to be checked.
    if not username:
        console.print(
            Panel(
                f"[Ansible Item] username for {normalized_image_name} could not be identified.",
                title="Error",
                style="red",
            )
        )
        # Exit with a non-zero status
        sys.exit(1)

    if os_status_code != 0:
        raise ClickException(os_message)
    else:
        # Build the message
        message = "[bold blue]🚀 Deployment Complete[/bold blue]\n"
        message += f"[bold]Item:[/bold] {server_name} server has been successfully deployed.\n\n"

        if not net.external_ip:
            if not external_ip_machine:
                initial_message_ip = (
                    "[bold yellow]⚠️ No external IP requested[/bold yellow]\n"
                )
            else:
                initial_message_ip = (
                    "[bold yellow]External IP already present[/bold yellow]\n"
                )
            message += f"{initial_message_ip}"
            message += "You can log in to the VM from another machine in your tenancy with:\n\n"
        else:
            message += (
                "[bold blue]🔐 VM Login Info[/bold blue]\n"
                "You can log in to the VM using:\n\n"
            )

        message += (
            f"[bold green]ssh -i [underline]{ssh_private_key_path}[/underline]"
            f" {username}@{external_ip_machine if external_ip_machine else internal_ip_machine}[/bold green]\n\n"
        )
        console.print(message)


@ewc_infra_command.command("show", help="Show Openstack server information.")  # type: ignore[misc]
@infra_context  # type: ignore[misc]
@openstack_options
@click.argument("server_name")  # type: ignore[misc]
def show_cmd(
    ctx: click.Context,
    server_name: str,
    federee: Optional[str] = None,
    auth_url: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
) -> None:
    """Show Server from Openstack."""
    federee = federee or ctx.cli_profile["federee"]

    try:
        # Step 1: Authenticate and initialize the OpenStack connection
        openstack_api = ctx.openstack_backend.connect(
            auth_url=auth_url,
            application_credential_id=application_credential_id,
            application_credential_secret=application_credential_secret,
        )
    except Exception as op_error:
        raise ClickException(
            f"Could not connect to Openstack due to the following error: {op_error}"
        )

    try:
        # Find the server info by name
        server_info = openstack_api.get_server(name_or_id=server_name)
    except Exception as e:
        raise ClickException(
            f"Could not retrieve server {server_name} from Openstack due to: {e}"
        )

    if not server_info:
        click.echo(f"Server '{server_name}' not found.")
        return

    image_id = server_info.get("image", "").get("id")
    image_info = openstack_api.image.find_image(image_id)

    image_name = image_info.get("name")

    vm_info = get_deployed_server_info(
        federee=federee,
        server_info=server_info,
        image_name=image_name,
    )

    list_server_details(vm_info)


@ewc_infra_command.command(name="list", help="List servers in Openstack.")  # type: ignore[misc]
@infra_context  # type: ignore[misc]
@openstack_options
@click.option(  # type: ignore[misc]
    "--show-all",
    is_flag=True,
    default=False,
    envvar="EWC_CLI_INFRA_LIST_FORCE_ENABLED",
    show_default=True,
    help="List machines even if not created by the EWC CLI.",
)
def list_cmd(
    ctx: click.Context,
    federee: Optional[str] = None,
    auth_url: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    show_all: bool = False,
) -> None:
    """List Servers from Openstack."""
    federee = federee or ctx.cli_profile["federee"]

    try:
        # Step 1: Authenticate and initialize the OpenStack connection
        openstack_api = ctx.openstack_backend.connect(
            auth_url=auth_url,
            application_credential_id=application_credential_id,
            application_credential_secret=application_credential_secret,
        )
    except Exception as op_error:
        raise ClickException(
            f"Could not connect to Openstack due to the following error: {op_error}"
        )

    try:
        servers = ctx.openstack_backend.list_servers(
            conn=openstack_api, show_all=show_all, federee=federee
        )
    except Exception as e:
        raise ClickException(
            f"Could not retrieve server list from Openstack due to: {e}"
        )
    list_server_table(servers=servers)


class ServerDeleteOptions(BaseModel):  # type: ignore[misc]
    dry_run: bool = False
    force: bool = False
    auth_url: Optional[str] = None
    application_credential_id: Optional[str] = None
    application_credential_secret: Optional[str] = None


@ewc_infra_command.command(name="delete", help="Delete server in Openstack.")  # type: ignore[misc]
@click.option(  # type: ignore[misc]
    "--dry-run",
    is_flag=True,
    default=False,
    help="Simulate the operation without making any changes.",
)
@click.argument(  # type: ignore[misc]
    "server-name",
    type=str,
)
@click.option(  # type: ignore[misc]
    "--force",
    is_flag=True,
    default=False,
    envvar="EWC_CLI_INFRA_DELETE_FORCE_ENABLED",
    show_default=True,
    help="Force deletion of machines not created by the ewccli.",
)
@infra_context  # type: ignore[misc]
@openstack_options
def delete_cmd(ctx: click.Context, server_name: str, opts: ServerDeleteOptions) -> None:
    """Delete VM from Openstack."""
    # Step 1: Authenticate and initialize the OpenStack connection
    try:
        # Step 1: Authenticate and initialize the OpenStack connection
        openstack_api = ctx.openstack_backend.connect(
            auth_url=opts.auth_url,
            application_credential_id=opts.application_credential_id,
            application_credential_secret=opts.application_credential_secret,
        )
    except Exception as op_error:
        raise ClickException(
            f"Could not connect to Openstack due to the following error: {op_error}"
        )

    server_name = os.getenv("EWC_CLI_OS_SERVER_NAME") or server_name

    try:
        ctx.openstack_backend.delete_server(
            conn=openstack_api,
            server_name=server_name,
            force=opts.force,
            dry_run=opts.dry_run,
        )
    except Exception as e:
        raise ClickException(
            f"Could not delete server {server_name} from Openstack due to: {e}"
        )


# def remove_server_external_ip(
#     federee: str,
#     application_credential_id: str,
#     application_credential_secret: str,
#     server_info: dict,
#     external_ip_machine: str,
#     auth_url: Optional[str] = None,
# ):
#     """Run post ansible operation if something goes wrong."""
#     try:
#         openstack_backend = OpenstackBackend(
#             application_credential_id=application_credential_id,
#             application_credential_secret=application_credential_secret,
#             auth_url=ewc_hub_config.EWC_CLI_SITE_MAP.get(federee),
#         )
#     except Exception as op_error:
#         return (
#             1,
#             f"Could not initialize Openstack config due to the following error: {op_error}",
#         )

#     try:
#         # Step 1: Authenticate and initialize the OpenStack connection
#         openstack_api = openstack_backend.connect(
#             auth_url=auth_url,
#             application_credential_id=application_credential_id,
#             application_credential_secret=application_credential_secret,
#         )
#     except Exception as op_error:
#         return (
#             1,
#             f"Could not connect to Openstack due to the following error: {op_error}",
#         )

#     # Remove external IP if not requested
#     openstack_backend.remove_external_ip(
#         conn=openstack_api, server=server_info, external_ip=external_ip_machine
#     )
