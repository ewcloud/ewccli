#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Common methods for all commands."""

import re
import sys
import os
import getpass
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import yaml
import rich_click as click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.markdown import Markdown
from rich.align import Align

from ewccli.backends.kubernetes.utils import get_reason_from_conditions
from ewccli.enums import HubItemOherAnnotation, HubItemCLIKeys
from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import load_cli_config, download_items
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


console = Console()


# Global state container
class CommonBackendContext:
    """CommonBackendContext."""

    def __init__(self):
        self.cli_config = load_cli_config(
            region=ewc_hub_config.EWC_CLI_DEFAULT_REGION,
            tenant_name=ewc_hub_config.EWC_CLI_DEFAULT_TENANCY_NAME,
        )


# Global state container
class HubContext:
    """HubContext."""

    def __init__(self):
        self.items = load_hub_items()


class CommonContext:
    """CommonContext."""

    def __init__(self):
        self.cli_config = load_cli_config(
            region=ewc_hub_config.EWC_CLI_DEFAULT_REGION,
            tenant_name=ewc_hub_config.EWC_CLI_DEFAULT_TENANCY_NAME,
        )
        self.items = load_hub_items()


def validate_config_name(ctx, param, value):
    """Validate config name."""
    if not value:
        return value

    pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
    if not re.match(pattern, value):
        raise click.BadParameter(
            "Config name must be exactly 4 alphanumeric parts separated by dashes (e.g. tenant-region-east-zone)."
        )
    return value


def login_options(func):
    """Login option for the CLI commands."""
    func = click.option(
        "--config-name",
        envvar="EWC_CLI_LOGIN_CONFIG_NAME",
        required=False,
        callback=validate_config_name,
        help="EWC CLI config name, format: {region}-{tenant_name} (all alphanumeric)",
    )(func)
    return func


def default_keypair_name():
    """Retrieve default keypair name from username."""
    # Safest way to get Linux username
    username = getpass.getuser()
    return f"{username}-ewccli-keypair"


# Compute default now for display purposes
KEYPAIT_DEFAULT = default_keypair_name()


def default_username():
    """Retrieve username runnnig the CLI."""
    # Safest way to get Linux username
    username = getpass.getuser()
    return f"{username}"


def load_hub_items() -> dict:
    """Load EWC Hub Items from file."""
    download_items()
    with open(ewc_hub_config.EWC_CLI_HUB_ITEMS_PATH, "r") as file:
        items_file = yaml.safe_load(file)

        if not items_file:
            _LOGGER.error("items.yaml is empty.")
            sys.exit(1)

        items_spec = items_file.get("spec")

        if not items_spec:
            _LOGGER.error("spec key is missing from items.yaml.")
            sys.exit(1)

        items = items_spec.get("items")

        if not items:
            _LOGGER.error("items key is missing from spec key in items.yaml.")
            sys.exit(1)

        return items


def split_config_name(config_name: str) -> tuple[str, str]:
    """
    Splits config_name into region and tenant_name.

    Assumes the format: <region>-<tenant-part1>-<tenant-part2>-<tenant-part3>

    :param config_name: The combined config name string.
    :return: A tuple (region, tenant_name).
    :raises ValueError: if config_name format is invalid.
    """
    parts = config_name.split("-")
    if len(parts) != 4:
        raise ValueError("config_name must have exactly 4 parts separated by '-'")
    region = parts[0]
    tenant_name = "-".join(parts[1:])
    return region, tenant_name


def openstack_options(func):
    """Openstack options for the CLI commands."""
    func = click.option(
        "--auth-url",
        "-url",
        required=False,
        envvar="OS_AUTH_URL",
        type=str,
        help="Openstack Auth URL. (or set env var OS_AUTH_URL)",
    )(func)
    func = click.option(
        "--application-credential-id",
        required=False,
        envvar="OS_APPLICATION_CREDENTIAL_ID",
        type=str,
        help="Openstack Application Credentials ID. (or set env var OS_APPLICATION_CREDENTIAL_ID)",
    )(func)
    func = click.option(
        "--application-credential-secret",
        required=False,
        envvar="OS_APPLICATION_CREDENTIAL_SECRET",
        type=str,
        help="Openstack Application Credentials Secret. (or set env var OS_APPLICATION_CREDENTIAL_SECRET)",
    )(func)

    return func


def _split_env_var(ctx, param, value) -> tuple:
    """Split env var or CLI input into a tuple of unique parameters."""
    if value is None:
        return ()

    if isinstance(value, tuple):
        raw_parameters = value
    else:
        raw_parameters = value.split(",")

    seen = set()
    unique_parameters = []
    for parameter in raw_parameters:
        parameter = parameter.strip()
        if parameter and parameter not in seen:
            seen.add(parameter)
            unique_parameters.append(parameter)

    return tuple(unique_parameters)


def openstack_optional_options(func):
    """Openstack optional options for the CLI commands."""
    func = click.option(
        "--networks",
        "-n",
        required=False,
        envvar="EWC_CLI_OPENSTACK_NETWORKS",
        type=str,
        multiple=True,
        callback=_split_env_var,
        help=(
            "List of networks (comma-separated in env var EWC_CLI_OPENSTACK_NETWORKS "
            "or multiple arguments with the flag)."
        ),
    )(func)
    func = click.option(
        "--security-groups",
        "-sg",
        required=False,
        envvar="EWC_CLI_OPENSTACK_SECURITY_GROUPS",
        type=str,
        multiple=True,
        callback=_split_env_var,
        help=(
            "List of security groups (comma-separated in env var EWC_CLI_OPENSTACK_SECURITY_GROUPS "
            "or multiple arguments with the flag)."
        ),
    )(func)
    func = click.option(
        "--keypair-name",
        "-kp",
        is_flag=False,
        required=False,
        default=default_keypair_name,  # callable, so evaluated at runtime
        envvar="EWC_CLI_OPENSTACK_KEYPAIR_NAME",
        show_default=KEYPAIT_DEFAULT,  # <-- override help display
        type=str,
        help=(
            "Select a name for the keypair in Openstack. "
            "(or set env var EWC_CLI_OPENSTACK_KEYPAIR_NAME)"
        ),
    )(func)
    func = click.option(
        "--image-name",
        "-ig",
        is_flag=False,
        required=False,
        envvar="EWC_CLI_OPENSTACK_IMAGE_NAME",
        show_default=True,
        type=str,
        help="Select image name to be used. (or set env var EWC_CLI_OPENSTACK_IMAGE_NAME)",
    )(func)
    func = click.option(
        "--flavour-name",
        "-fr",
        is_flag=False,
        required=False,
        envvar="EWC_CLI_OPENSTACK_FLAVOUR_NAME",
        show_default=True,
        type=str,
        help="Select a name for the keypair in Openstack. (or set env var EWC_CLI_OPENSTACK_FLAVOUR_NAME)",
    )(func)
    func = click.option(
        "--external-ip",
        is_flag=True,
        default=False,
        envvar="EWC_CLI_EXTERNAL_IP",
        type=bool,
        show_default=True,
        help="Add External IP to the machine.",
    )(func)

    return func


def ssh_options_encoded(func):
    """SSH options encoded for the CLI commands."""
    func = click.option(
        "--ssh-private-encoded",
        required=False,
        envvar="EWC_CLI_ENCODED_SSH_PRIVATE_KEY",
        type=str,
        help="Base64 encoded SSH private key.",
    )(func)
    func = click.option(
        "--ssh-public-encoded",
        required=False,
        envvar="EWC_CLI_ENCODED_SSH_PUBLIC_KEY",
        type=str,
        help="Base64 encoded SSH public key.",
    )(func)

    return func


def validate_path(ctx, param, value):
    """Validate path."""
    try:
        # Expand ~ and resolve to absolute path
        path = Path(value).expanduser().resolve(strict=False)

        # Check if parent directory exists or is creatable
        parent = path.parent
        if not parent.exists():
            try:
                # Try to create it temporarily (then delete)
                parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise click.BadParameter(f"Cannot create directory '{parent}': {e}")

        # Check for invalid characters (especially on Windows)
        invalid_chars = set('<>:"|?*') if os.name == "nt" else set()
        if any(char in invalid_chars for char in str(path)):
            raise click.BadParameter(f"The path '{path}' contains invalid characters.")

        return path  # Return as a Path object

    except Exception as e:
        raise click.BadParameter(f"Invalid path '{value}': {e}")


def ssh_options(func):
    """SSH options for the CLI commands."""
    func = click.option(
        "--ssh-public-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PUBLIC_KEY_PATH",
        type=str,
        default=ewc_hub_config.EWC_CLI_PUBLIC_SSH_KEY_PATH,
        help="Path to SSH public key.",
        callback=validate_path,
    )(func)
    func = click.option(
        "--ssh-private-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PRIVATE_KEY_PATH",
        type=str,
        default=ewc_hub_config.EWC_CLI_PRIVATE_SSH_KEY_PATH,
        help="Path to SSH private key.",
        callback=validate_path,
    )(func)

    return func


def list_items_table(hub_items: dict):
    """List items in table."""
    table = Table(
        show_header=True,
        header_style="bold green",
        title="EWC HUB Items",
        box=box.MINIMAL_DOUBLE_HEAD,
    )
    table.add_column("Item")
    table.add_column("Title")
    table.add_column("Version")
    table.add_column("Summary")
    # table.add_column("Description")

    for item, item_v in hub_items.items():
        annotations = item_v.get("annotations")

        if not annotations:
            continue

        others_annotations = annotations.get("others", "").split(",")

        # Filter items not EWCCLI compatible
        if HubItemOherAnnotation.EWCCLI_COMPATIBLE.value not in  others_annotations:
            continue

        table.add_row(
            item,
            item_v.get("displayName"),
            item_v.get("version"),
            item_v.get("summary"),
        )

    console.print(
        table,
        # justify="center"
    )


def show_item_table(hub_item: dict, default_admin_variables_map: Optional[dict] = None):
    """Show item metadata table."""
    table = Table(
        show_header=True,
        show_lines=True,
        header_style="bold green",
        title=f"{hub_item.get('name')} EWC Item Details",
        box=box.MINIMAL_DOUBLE_HEAD,
    )
    table.add_column("Metadata", no_wrap=False, min_width=15)
    table.add_column("Data", no_wrap=False, min_width=15)

    table.add_row("name", hub_item.get("name"))
    table.add_row("version", hub_item.get("version"))
    table.add_row("summary", hub_item.get("summary"))

    for maintainer in hub_item.get("maintainers", {}):
        if maintainer.get("url"):
            table.add_row(
                "maintainer",
                f"[bold]{maintainer.get('name')}:[/bold] [link={maintainer.get('url')}]{maintainer.get('url')}",
            )
        else:
            table.add_row(
                f"maintainer: {maintainer.get('name')}",
                f"[link={maintainer.get('email')}]{maintainer.get('email')}",
            )
    table.add_row("home", f"[link={hub_item.get('home')}]{hub_item.get('home')}")
    table.add_row(
        "license", f"[link={hub_item.get('license')}]{hub_item.get('license')}"
    )

    for annotation, a_v in hub_item.get("annotations", {}).items():
        table.add_row(annotation, a_v)

    md_description = Markdown(hub_item.get("description"))
    table.add_row("description", Align(md_description, align="left", width=80))

    deploy_command_example = f"ewc hub deploy {hub_item.get('name')}"

    if not default_admin_variables_map:
        default_admin_variables_map = {}
    default_admin_variables = [dav for dav in default_admin_variables_map]

    details = ""
    item_info_ewccli = hub_item.get(HubItemCLIKeys.ROOT.value, {})

    for mi in item_info_ewccli.get(HubItemCLIKeys.INPUTS.value, []):
        var_name = mi.get("name")
        default_str = f" (default: {mi['default']})" if "default" in mi else ""
        mandatory = (
            "(mandatory)"
            if ("default" not in mi and var_name not in default_admin_variables)
            else "(optional) "
        )
        details += f"{mandatory} {var_name}: ({mi.get('type')}){default_str}: {mi.get('description')}\n"

        if "default" not in mi and var_name not in default_admin_variables:
            deploy_command_example += f" --item-inputs {var_name}='<>'"

    table.add_row("Inputs", details)

    table.add_row("Deploy command example", deploy_command_example)

    deploy_command_defaults = ""
    if item_info_ewccli.get(HubItemCLIKeys.DEFAULT_IMAGE_NAME.value):
        deploy_command_defaults = f"Image Name: {item_info_ewccli.get(HubItemCLIKeys.DEFAULT_IMAGE_NAME.value)}\n"

    if item_info_ewccli.get(HubItemCLIKeys.DEFAULT_SECURITY_GROUPS.value):
        deploy_command_defaults = f"Security Group/s: {','.join([f for f in item_info_ewccli.get(HubItemCLIKeys.DEFAULT_SECURITY_GROUPS.value, [])])}\n"

    if deploy_command_defaults:
        table.add_row("Deploy command defaults", deploy_command_defaults)

    console.print(
        table,
        # justify="center"
    )


def list_dict_table(title: str, kv: dict):
    """List dictionary in table."""
    table = Table(
        show_header=True,
        header_style="bold green",
        title=title,
        box=box.MINIMAL_DOUBLE_HEAD,
    )
    table.add_column("Keys")
    table.add_column("Value")

    for item_k, item_v in kv.items():
        if isinstance(item_v, list):
            item_v = ",".join(item_v)

        table.add_row(item_k, item_v)

    console.print(
        table,
        # justify="center"
    )


def show_objects(title: str, objects: list, plural: str, namespace: str) -> None:
    """Show objects from kubernetes backend."""
    if not objects:
        click.echo(f"No {plural} found.")
        return None


    table = Table(title=title)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Namespace", style="yellow")
    table.add_column("Age", style="green")
    table.add_column("Status", style="magenta")

    now = datetime.now(timezone.utc)

    for item in objects:
        metadata = item.get("metadata", {})
        name = metadata.get("name", "N/A")
        namespace = metadata.get("namespace", namespace)
        creation_ts = metadata.get("creationTimestamp")
        status_obj = item.get("status", {})
        conditions = status_obj.get("conditions", [])

        status = get_reason_from_conditions(conditions)

        age = "N/A"
        if creation_ts:
            created = datetime.fromisoformat(creation_ts.replace("Z", "+00:00"))
            age_seconds = (now - created).total_seconds()
            if age_seconds < 60:
                age = f"{int(age_seconds)}s"
            elif age_seconds < 3600:
                age = f"{int(age_seconds // 60)}m"
            elif age_seconds < 86400:
                age = f"{int(age_seconds // 3600)}h"
            else:
                age = f"{int(age_seconds // 86400)}d"

        table.add_row(name, namespace, age, status)

    console.print(table)


def describe_object(obj: dict) -> None:
    """
    Render a Kubernetes object (CR or built-in) in a kubectl-describe-like table.
    """
    if not obj:
        return None

    def _flatten(d, parent=""):
        """Flatten dicts into key: value (dot notation for nested)."""
        items = []
        for k, v in d.items():
            key = f"{parent}.{k}" if parent else k
            if isinstance(v, dict):
                items.extend(_flatten(v, key))
            elif isinstance(v, list):
                if all(isinstance(i, dict) for i in v):
                    for idx, sub in enumerate(v):
                        items.extend(_flatten(sub, f"{key}[{idx}]"))
                else:
                    items.append((key, ", ".join(str(i) for i in v)))
            else:
                items.append((key, v))
        return items

    # Flatten top-level metadata, spec, status
    sections = {
        "Metadata": obj.get("metadata", {}),
        "Spec": obj.get("spec", {}),
        "Status": obj.get("status", {}),
    }

    # Print header
    click.secho(f"Name: {obj.get('metadata', {}).get('name', '<unknown>')}", fg="cyan", bold=True)
    click.secho(f"Namespace: {obj.get('metadata', {}).get('namespace', '<default>')}", fg="cyan")
    click.secho(f"Kind: {obj.get('kind', '<unknown>')} | API: {obj.get('apiVersion', '')}", fg="cyan")
    click.echo()

    # Print sections
    for section, content in sections.items():
        if not content:
            continue
        click.secho(section, fg="green", bold=True)
        for key, value in _flatten(content):
            click.echo(f"  {key:25} {value}")
        click.echo()
