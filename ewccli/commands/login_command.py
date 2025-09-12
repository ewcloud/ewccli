#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Login: EWC Login interaction."""

import os
import re
from pathlib import Path

import rich_click as click
from rich.console import Console

from prompt_toolkit.application import Application
from prompt_toolkit.widgets import RadioList, Box, Frame
from prompt_toolkit.layout import Layout
from prompt_toolkit.styles import Style

from kubernetes import config
from kubernetes.config.config_exception import (  # noqa: N813
    ConfigException as kubernetes_config_exception,
)
from openstack.config import OpenStackConfig
from openstack.exceptions import (  # noqa: N813
    ConfigException as openstack_config_exception,
)

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import save_cli_config, generate_ssh_keypair
from ewccli.enums import Federee
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


console = Console()


def kubeconfig_available():
    """Verify if kubeconfig is available."""
    try:
        config.load_kube_config()
        return True
    except kubernetes_config_exception as e:
        _LOGGER.warning(
            f"⚠️ Kubeconfig not found: {e}\n"
            "You could set KUBECONFIG=/path/to/your/kubeconfig or continue below using the token"
        )
        return False


def cloud_yaml_exists():
    """Check if OpenStack clouds.yaml file exists."""
    # Default OpenStack config paths (can vary by environment)
    default_paths = [
        Path(
            os.getenv("OS_CLIENT_CONFIG_FILE", "~/.config/openstack/clouds.yaml")
        ).expanduser(),
        Path("/etc/openstack/clouds.yaml"),
    ]

    return any(p.exists() for p in default_paths)


def openstack_config_available():
    """Verify if OpenStack cloud config is available."""
    try:
        os_config = OpenStackConfig()
        if cloud_yaml_exists():
            os_config.get_one_cloud()
        else:
            _LOGGER.warning(
                "⚠️ OpenStack cloud config not found at '~/.config/openstack/cloud.yaml'\n"
                "You can set the config path with the environment variable:\n"
                "  OS_CLIENT_CONFIG_FILE=/path/to/clouds.yaml\n"
                "Alternatively, provide your credentials using:\n"
                "  OS_APPLICATION_CREDENTIAL_ID and OS_APPLICATION_CREDENTIAL_SECRET\n"
                "Or continue below to enter them manually."
            )
            return False
        return True
    except openstack_config_exception as e:
        _LOGGER.warning(
            f"⚠️ OpenStack cloud config not found: {e}\n"
            "You can also set the config path with `OS_CLIENT_CONFIG_FILE=/path/to/clouds.yaml` or continue below"
        )
        return False


def validate_tenant_name(ctx, param, value):
    """Validate tenant name."""
    pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
    if not re.match(pattern, value):
        raise click.BadParameter(
            "Config name must be exactly 3 alphanumeric parts separated by dashes (e.g. thisis-my-tenancy)."
        )
    return value


def init_options(func):
    """Login options for the CLI login command."""
    func = click.option(
        "--tenant-name",
        envvar="EWC_CLI_LOGIN_TENANT_NAME",
        prompt=True,
        required=True,
        callback=validate_tenant_name,
        help=(
            "Name of your tenancy in EWC, used to identify cloud configurations.\n"
            "Must follow the format: 'part1-part2-part3' (e.g. 'demo-user-eu'), "
            "where each part is alphanumeric and separated by dashes.\n"
            "Can also be set via the EWC_CLI_LOGIN_TENANT_NAME environment variable."
        ),
    )(func)
    func = click.option(
        "--region",
        type=click.Choice(
            [Federee.ECMWF.value, Federee.EUMETSAT.value], case_sensitive=True
        ),
        envvar="EWC_CLI_LOGIN_REGION",
        help=(
            "Cloud region where the resources will be deployed. "
            "You can also set this using the EWC_CLI_LOGIN_REGION environment variable. "
            "If not provided, you'll be prompted to choose."
        ),
    )(func)
    func = click.option(
        "--application-credential-id",
        required=False,
        hide_input=True,
        help=(
            "OpenStack Application Credential ID. "
            "Ignored if environment variable OS_APPLICATION_CREDENTIAL_ID is set, "
            "or if a cloud.yaml config is found at '~/.config/openstack/cloud.yaml' "
            "or at the path specified by OS_CLIENT_CONFIG_FILE."
        ),
    )(func)
    func = click.option(
        "--application-credential-secret",
        required=False,
        hide_input=True,
        help=(
            "OpenStack Application Credential Secret. "
            "Ignored if environment variable OS_APPLICATION_CREDENTIAL_SECRET is set, "
            "or if a cloud.yaml config is found at '~/.config/openstack/cloud.yaml' "
            "or at the path specified by OS_CLIENT_CONFIG_FILE."
        ),
    )(func)
    # func = click.option(
    #     "--token",
    #     hide_input=True,
    #     required=False,
    #     default="",
    #     help=(
    #         "Kubernetes token (leave blank if not needed).\n"
    #         "Provide this only if you plan to use Kubernetes services and "
    #         "do not have a kubeconfig file available "
    #         "(e.g. ~/.kube/config or via the KUBECONFIG environment variable)."
    #     ),
    # )(func)
    func = click.option(
        "--ssh-public-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PUBLIC_KEY_PATH",
        type=str,
        default=ewc_hub_config.EWC_CLI_PUBLIC_SSH_KEY_PATH,
        help="Path to SSH public key.",
    )(func)
    func = click.option(
        "--ssh-private-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PRIVATE_KEY_PATH",
        type=str,
        default=ewc_hub_config.EWC_CLI_PRIVATE_SSH_KEY_PATH,
        help="Path to SSH private key.",
    )(func)

    return func


def select_provider():
    """Select provider."""
    choices = [
        ("EUMETSAT", "EUMETSAT"),
        ("ECMWF", "ECMWF"),
    ]

    radio_list = RadioList(choices)

    # Use the widget's own default key bindings
    kb = radio_list.control.key_bindings

    @kb.add("enter")
    def _(event):
        index = radio_list._selected_index
        selected_value = radio_list.values[index][
            1
        ]  # values is list of tuples (display, value)
        event.app.exit(result=selected_value)

    # Add quit keys as well
    @kb.add("c-c")
    @kb.add("c-q")
    def _(event):
        event.app.exit(None)

    root_container = Box(Frame(radio_list, title="Select Region"), padding=1)
    layout = Layout(root_container)

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=True,
        style=Style.from_dict(
            {
                "frame.label": "bold",
            }
        ),
    )

    selected = app.run()
    return selected


def check_and_generate_ssh_keys(
    ssh_public_key_path: str,
    ssh_private_key_path: str,
):
    """Check for SSH keys, prompt to generate if missing"""
    private_exists = Path(ssh_private_key_path).exists()
    public_exists = Path(ssh_public_key_path).exists()

    if private_exists and public_exists:
        console.print("SSH key pair already exists.")
    else:
        console.print("SSH key pair is missing.")
        if click.confirm("Do you want to generate a new SSH key pair?", default=False):
            generate_ssh_keypair(
                ssh_public_key_path=ssh_public_key_path,
                ssh_private_key_path=ssh_private_key_path,
            )
        else:
            click.echo("SSH key generation skipped. Exiting.")


def init_command(
    application_credential_id: str,
    application_credential_secret: str,
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    tenant_name: str,
    region: str,
    # token: str,
):
    """EWC CLI Login."""
    if not region:
        # If --region is not passed, ask interactively
        region = select_provider()
        if not region:
            console.print("No selection made. Exiting.")
            return

    console.print(f"Considering region: {region}")

    check_and_generate_ssh_keys(
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
    )

    if openstack_config_available():
        console.print(
            "🔑 [bold green]Openstack cloud.yaml found at ~/.config/openstack/clouds.yaml[/bold green]"
            " – skipping Openstack ID and secret requirements."
        )
        application_credential_id = ""
        application_credential_secret = ""

    elif not application_credential_id or not application_credential_secret:
        if not application_credential_id:
            # Handle OpenStack credential ID
            application_credential_id = (
                application_credential_id
                or os.getenv("OS_APPLICATION_CREDENTIAL_ID")
                or click.prompt(
                    "Enter OpenStack Application Credential ID", hide_input=True
                )
            )

        if not application_credential_secret:
            # Handle OpenStack credential secret
            application_credential_secret = (
                application_credential_secret
                or os.getenv("OS_APPLICATION_CREDENTIAL_SECRET")
                or click.prompt(
                    "Enter OpenStack Application Credential Secret", hide_input=True
                )
            )

    # if kubeconfig_available():
    #     click.echo("🔑 kubeconfig found – skipping token requirement.")
    #     token = None
    # elif not token:
    #     token = click.prompt(
    #         "Enter Kubernetes token (leave blank if not needed)",
    #         hide_input=True,
    #         default="",
    #         show_default=False,
    #         prompt_suffix=": ",
    #     )
    #     if token == "":
    #         token = None

    # Save config
    save_cli_config(
        region=region,
        tenant_name=tenant_name,
        # token=token,
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
    )
    console.print(
        f"✅ Configuration saved for tenant '[bold cyan]{tenant_name}[/bold cyan]' "
        f"in the following directory {ewc_hub_config.EWC_CLI_BASE_PATH}"
    )
