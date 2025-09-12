#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""EWC CLI: VM interaction."""

import os
from typing import Optional

import rich_click as click
from rich.console import Console
from rich.table import Table
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
from ewccli.commands.commons import split_config_name
from ewccli.commands.commons_infra import get_deployed_server_info, list_server_details
from ewccli.commands.commons_infra import deploy_server
from ewccli.utils import load_cli_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)

console = Console()

infra_context = click.make_pass_decorator(CommonBackendContext, ensure=True)


# Command Group
@click.group(name="infra")
@infra_context
@login_options
def ewc_infra_command(ctx, config_name):
    """EWC Infrastructure commands group."""
    if config_name:
        region, tenant_name = split_config_name(config_name=config_name)
        ctx.cli_config = load_cli_config(tenant_name=tenant_name, region=region)

    region = ctx.cli_config.get("region")
    application_credential_id = ctx.cli_config.get("application_credential_id")
    application_credential_secret = ctx.cli_config.get("application_credential_secret")
    ctx.openstack_backend = OpenstackBackend(
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
        auth_url=ewc_hub_config.EWC_CLI_SITE_MAP.get(region),
    )


def list_server_table(servers: dict):
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


@ewc_infra_command.command("create", help="Create server in Openstack.")
@infra_context
@ssh_options
@ssh_options_encoded
@openstack_options
@openstack_optional_options
@click.option(
    "--dry-run",
    envvar="EWC_CLI_DRY_RUN",
    default=False,
    is_flag=True,
    help="Simulate deployment without running.",
)
@click.option(
    "--force",
    envvar="EWC_CLI_FORCE",
    is_flag=True,
    default=False,
    help="Force item recreation operation.",
)
@click.argument("server_name")
def create_cmd(
    ctx,
    server_name,
    dry_run: bool,
    force: bool,
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    keypair_name: str,
    config_name: Optional[str] = None,
    region: Optional[str] = None,
    auth_url: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    image_name: Optional[str] = None,
    flavour_name: Optional[str] = None,
    external_ip: bool = False,
    networks: Optional[tuple] = None,
    security_groups: Optional[tuple] = None,
    ssh_private_encoded: Optional[str] = None,
    ssh_public_encoded: Optional[str] = None,
    ):
    """Show Server from Openstack."""
    if dry_run:
        _LOGGER.info("Dry run enabled...")

    if config_name:
        retrieve_region, tenant_name = split_config_name(config_name=config_name)
        cli_config = load_cli_config(tenant_name=tenant_name, region=retrieve_region)
    else:
        cli_config = load_cli_config()

    federee = region or cli_config["region"]

    _LOGGER.info(f"The server will be deployed on {federee} side of the EWC.")

    #####################################################################################
    # Authenticate to Openstack
    #####################################################################################

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

    server_inputs = {
        "server_name": server_name,
        "is_gpu": None,
        "image_name": image_name,
        "keypair_name": keypair_name,
        "flavour_name": flavour_name,
        "external_ip": external_ip,
        "networks": networks,
        "security_groups": security_groups,
    }

    os_status_code, os_message, outputs = deploy_server(
        openstack_backend=ctx.openstack_backend,
        openstack_api=openstack_api,
        federee=federee,
        server_inputs=server_inputs,
        ssh_private_encoded=ssh_private_encoded,
        ssh_public_encoded=ssh_public_encoded,
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
        dry_run=dry_run,
        force=force,
    )

    if not outputs:
        raise ClickException(os_message)

    username = outputs.get("username")
    # server_info = outputs.get("server_info")
    # external_network = outputs.get("external_network")
    internal_ip_machine = outputs["internal_ip_machine"]
    external_ip_machine = outputs.get("external_ip_machine")

    if os_status_code != 0:
        raise ClickException(os_message)
    else:
        # Build the message
        message = "[bold blue]🚀 Deployment Complete[/bold blue]\n"
        message += f"[bold]Item:[/bold] {server_name} server has been successfully deployed.\n\n"

        if not external_ip:
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


@ewc_infra_command.command("show", help="Show Openstack server information.")
@infra_context
@openstack_options
@click.argument("server_name")
def show_cmd(
    ctx,
    server_name,
    region: Optional[str] = None,
    auth_url: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    ):
    """Show Server from Openstack."""
    federee = region or ctx.cli_config["region"]

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

    image_name = image_info.get('name')

    vm_info = get_deployed_server_info(
        federee=federee,
        server_info=server_info,
        image_name=image_name,
    )

    list_server_details(vm_info)


@ewc_infra_command.command(name="list", help="List servers in Openstack.")
@infra_context
@openstack_options
@click.option(
    "--show-all",
    is_flag=True,
    default=False,
    envvar="EWC_CLI_INFRA_LIST_FORCE_ENABLED",
    show_default=True,
    help="List machines even if not created by the EWC CLI.",
)
def list_cmd(
    ctx,
    region: Optional[str] = None,
    auth_url: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    show_all: bool = False,
):
    """List Servers from Openstack."""
    federee = region or ctx.cli_config["region"]

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


@ewc_infra_command.command(name="delete", help="Delete server in Openstack.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Simulate the operation without making any changes.",
)
@click.argument(
    "server-name",
    type=str,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    envvar="EWC_CLI_INFRA_DELETE_FORCE_ENABLED",
    show_default=True,
    help="Force deletion of machines not created by the ewccli.",
)
@infra_context
@openstack_options
def delete_cmd(
    ctx,
    server_name: str,
    force: bool = False,
    auth_url: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    dry_run: bool = False,
):
    """Delete VM from Openstack."""
    # Step 1: Authenticate and initialize the OpenStack connection
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

    server_name = os.getenv("EWC_CLI_OS_SERVER_NAME") or server_name

    try:
        ctx.openstack_backend.delete_server(
            conn=openstack_api, server_name=server_name, force=force, dry_run=dry_run
        )
    except Exception as e:
        raise ClickException(
            f"Could not delete server {server_name} from Openstack due to: {e}"
        )

# def remove_server_external_ip(
#     region: str,
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
#             auth_url=ewc_hub_config.EWC_CLI_SITE_MAP.get(region),
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

