#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Common methods for all commands."""

from __future__ import annotations

import re
import sys
import os
import getpass
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from typing import Callable
from datetime import datetime, timezone

import yaml
import rich_click as click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.markdown import Markdown
from rich.align import Align

from ewccli.backends.kubernetes.utils import get_reason_from_conditions
from ewccli.enums import HubItemOherAnnotation
from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import download_items
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


console = Console()


# Global state container
class CommonBackendContext:
    """CommonBackendContext."""

    def __init__(self) -> None:
        self.cli_profile: Any = None


class CommonContext:
    """CommonContext."""

    def __init__(self) -> None:
        self.cli_profile: Any = None
        self.items: dict[str, Any] = load_hub_items()


def validate_config_name(
    ctx: click.Context,
    param: click.Parameter,
    value: Optional[str],
) -> Optional[str]:
    """Validate config name."""
    if value is None:
        return None

    pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
    if not re.match(pattern, value):
        raise click.BadParameter(
            "Config name must be exactly 4 alphanumeric parts separated by dashes "
            "(e.g. tenant-federee-east-zone)."
        )

    return value


def login_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Login option for the CLI commands."""
    func = click.option(
        "--profile",
        envvar="EWC_CLI_LOGIN_PROFILE",
        required=False,
        help="EWC CLI profile name",
    )(func)
    return func


def default_keypair_name() -> str:
    """Retrieve default keypair name from username."""
    # Safest way to get Linux username
    username = getpass.getuser()
    return f"{username}-ewccli-keypair"


# Compute default now for display purposes
KEYPAIT_DEFAULT = default_keypair_name()


def default_username() -> str:
    """Retrieve username runnnig the CLI."""
    # Safest way to get Linux username
    username = getpass.getuser()
    return f"{username}"


def load_hub_items(
    path_to_catalog: Path = ewc_hub_config.EWC_CLI_HUB_ITEMS_PATH,
) -> Dict[str, Any]:
    """Load EWC Hub Items from file."""
    download_items()
    with open(path_to_catalog, "r", encoding="utf-8") as file:
        items_file = yaml.safe_load(file)

    if not isinstance(items_file, dict):
        _LOGGER.error("items.yaml is malformed or empty.")
        sys.exit(1)

    items_spec = items_file.get("spec")
    if not isinstance(items_spec, dict):
        _LOGGER.error("spec key is missing or invalid in items.yaml.")
        sys.exit(1)

    items = items_spec.get("items")
    if not isinstance(items, dict):
        _LOGGER.error("items key is missing or invalid under spec in items.yaml.")
        sys.exit(1)

    # At this point, mypy knows `items` is a dict[str, Any]
    return items


def split_config_name(config_name: str) -> tuple[str, str]:
    """
    Splits config_name into federee and tenant_name.

    Assumes the format: <federee>-<tenant-part1>-<tenant-part2>-<tenant-part3>

    :param config_name: The combined config name string.
    :return: A tuple (federee, tenant_name).
    :raises ValueError: if config_name format is invalid.
    """
    parts = config_name.split("-")
    if len(parts) != 4:
        raise ValueError("config_name must have exactly 4 parts separated by '-'")
    federee = parts[0]
    tenant_name = "-".join(parts[1:])
    return federee, tenant_name


def openstack_options(func: Callable[..., Any]) -> Callable[..., Any]:
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


def _split_env_var(
    ctx: click.Context,
    param: click.Parameter,
    value: Optional[str | Tuple[str, ...]],
) -> Tuple[str, ...]:
    """Split env var or CLI input into a tuple of unique parameters."""
    if value is None:
        return ()

    if isinstance(value, tuple):
        raw_parameters = value
    else:
        raw_parameters = tuple(value.split(","))

    seen: set[str] = set()
    unique_parameters: list[str] = []

    for parameter in raw_parameters:
        p = parameter.strip()
        if p and p not in seen:
            seen.add(p)
            unique_parameters.append(p)

    return tuple(unique_parameters)


def openstack_optional_options(func: Callable[..., Any]) -> Callable[..., Any]:
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


def ssh_options_encoded(func: Callable[..., Any]) -> Callable[..., Any]:
    """SSH options encoded for the CLI commands."""
    func = click.option(
        "--ssh-private-encoded",
        required=False,
        envvar="EWC_CLI_ENCODED_SSH_PRIVATE_KEY",
        type=str,
        help="Base64 encoded SSH private key. (or set env var EWC_CLI_ENCODED_SSH_PRIVATE_KEY)",
    )(func)
    func = click.option(
        "--ssh-public-encoded",
        required=False,
        envvar="EWC_CLI_ENCODED_SSH_PUBLIC_KEY",
        type=str,
        help="Base64 encoded SSH public key. (or set env var EWC_CLI_ENCODED_SSH_PUBLIC_KEY)",
    )(func)

    return func


def validate_path(
    ctx: click.Context,
    param: click.Parameter,
    value: Optional[str],
) -> Optional[Path]:
    """Validate and normalize a filesystem path for CLI parameters."""
    if not value:
        return None
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


def ssh_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """SSH options for the CLI commands."""
    func = click.option(
        "--ssh-public-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PUBLIC_KEY_PATH",
        type=str,
        help="Path to SSH public key. (or set env var EWC_CLI_SSH_PUBLIC_KEY_PATH)",
        callback=validate_path,
    )(func)
    func = click.option(
        "--ssh-private-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PRIVATE_KEY_PATH",
        type=str,
        help="Path to SSH private key. (or set env var EWC_CLI_SSH_PRIVATE_KEY_PATH)",
        callback=validate_path,
    )(func)

    return func


def list_items_table(hub_items: Dict[str, Any]) -> None:
    """List items in table."""
    table = Table(
        show_header=True,
        header_style="bold green",
        title="EWC HUB Items",
        box=box.MINIMAL_DOUBLE_HEAD,
    )
    table.add_column("Item", overflow="fold")
    table.add_column("Title")
    table.add_column("Version")
    table.add_column("Summary")
    # table.add_column("Description")

    for item, item_v in hub_items.items():
        annotations = item_v.get("annotations")
        if not annotations:
            _LOGGER.warning(f"Filtering {item} as it doesn't contain annotations.")
            continue

        others_annotations = annotations.get("others", "").split(",")

        # Filter items not EWCCLI compatible
        if HubItemOherAnnotation.EWCCLI_COMPATIBLE.value not in others_annotations:
            _LOGGER.warning(
                f"Filtering {item} as this is not compatible with the EWCCLI according to the catalog:"
                f"\n`{HubItemOherAnnotation.EWCCLI_COMPATIBLE.value}` annotation is not in `others` annotations list."
            )
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


def _add_basic_metadata(table: Table, hub_item: Dict[str, Any]) -> None:
    table.add_row("name", hub_item.get("name"))
    table.add_row("version", hub_item.get("version"))
    table.add_row("summary", hub_item.get("summary"))


def _add_maintainers(table: Table, hub_item: Dict[str, Any]) -> None:
    for maintainer in hub_item.get("maintainers", []):
        name = maintainer.get("name")
        url = maintainer.get("url")
        email = maintainer.get("email")

        if url:
            table.add_row(
                "maintainer",
                f"[bold]{name}:[/bold] [link={url}]{url}",
            )
        else:
            table.add_row(
                f"maintainer: {name}",
                f"[link={email}]{email}",
            )


def _add_annotations(table: Table, hub_item: Dict[str, Any]) -> None:
    for key, value in hub_item.get("annotations", {}).items():
        table.add_row(key, value)


def _add_description(table: Table, hub_item: Dict[str, Any]) -> None:
    md = Markdown(hub_item.get("description"))
    table.add_row("description", Align(md, align="left", width=80))


def _extract_default_admin_vars(default_map: Optional[Dict[str, Any]]) -> List[str]:
    if not default_map:
        return []
    return list(default_map)


def _input_is_mandatory(mi: Dict[str, Any], default_admin_vars: List[str]) -> bool:
    name = mi.get("name")
    return "default" not in mi and name not in default_admin_vars


def _format_default(mi: Dict[str, Any]) -> str:
    if "default" in mi:
        return f" (default: {mi['default']})"
    return ""


def _format_input_line(mi: Dict[str, Any], mandatory: bool, default_str: str) -> str:
    name = mi.get("name")
    type_ = mi.get("type")
    desc = mi.get("description")
    tag = "(mandatory)" if mandatory else "(optional)"
    return f"{tag} {name}: ({type_}){default_str}: {desc}\n"


def _maybe_add_to_deploy_cmd(
    deploy_cmd: str,
    mi: Dict[str, Any],
    mandatory: bool,
) -> str:
    if mandatory:
        name = mi.get("name")
        return f"{deploy_cmd} --item-inputs {name}='<>'"
    return deploy_cmd


def _render_inputs(
    item_info: Dict[str, Any],
    default_admin_vars: List[str],
    deploy_cmd: str,
) -> tuple[str, str]:
    details = ""

    for mi in item_info.get("inputs", []):
        mandatory = _input_is_mandatory(mi, default_admin_vars)
        default_str = _format_default(mi)

        details += _format_input_line(mi, mandatory, default_str)
        deploy_cmd = _maybe_add_to_deploy_cmd(deploy_cmd, mi, mandatory)

    return details, deploy_cmd


def _render_defaults(item_info: Dict[str, Any]) -> str:
    defaults = []

    image = item_info.get("defaultImageName")
    if image:
        defaults.append(f"Image Name: {image}")

    sgs = item_info.get("defaultSecurityGroups", [])
    if sgs:
        defaults.append(f"Security Group/s: {','.join(sgs)}")

    return "\n".join(defaults) + ("\n" if defaults else "")


def show_item_table(
    hub_item: Dict[str, Any],
    default_admin_variables_map: Optional[Dict[str, Any]] = None,
) -> None:
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

    _add_basic_metadata(table, hub_item)
    _add_maintainers(table, hub_item)
    _add_annotations(table, hub_item)
    _add_description(table, hub_item)

    item_info = hub_item.get("ewccli", {})
    default_admin_vars = _extract_default_admin_vars(default_admin_variables_map)

    deploy_cmd = f"ewc hub deploy {hub_item.get('name')}"
    inputs_details, deploy_cmd = _render_inputs(
        item_info, default_admin_vars, deploy_cmd
    )

    table.add_row("Inputs", inputs_details)
    table.add_row("Deploy command example", deploy_cmd)

    defaults_block = _render_defaults(item_info)
    if defaults_block:
        table.add_row("Deploy command defaults", defaults_block)

    console.print(table)


def list_dict_table(title: str, kv: Dict[str, Any]) -> None:
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


def _extract_metadata(item: Dict[str, Any], default_ns: str) -> tuple[str, str, str]:
    metadata = item.get("metadata", {})
    name = metadata.get("name", "N/A")
    namespace = metadata.get("namespace", default_ns)
    creation_ts = metadata.get("creationTimestamp")
    return name, namespace, creation_ts


def _compute_age(creation_ts: str | None, now: datetime) -> str:
    if not creation_ts:
        return "N/A"

    created = datetime.fromisoformat(creation_ts.replace("Z", "+00:00"))
    age_seconds = (now - created).total_seconds()

    if age_seconds < 60:
        value, unit = int(age_seconds), "s"
    elif age_seconds < 3600:
        value, unit = int(age_seconds // 60), "m"
    elif age_seconds < 86400:
        value, unit = int(age_seconds // 3600), "h"
    else:
        value, unit = int(age_seconds // 86400), "d"

    return f"{value}{unit}"


def _extract_status(item: Dict[str, Any]) -> Any:
    status_obj = item.get("status", {})
    conditions = status_obj.get("conditions", [])
    return get_reason_from_conditions(conditions)


def _build_table(title: str) -> Table:
    table = Table(title=title)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Namespace", style="yellow")
    table.add_column("Age", style="green")
    table.add_column("Status", style="magenta")
    return table


def show_objects(
    title: str, objects: List[Dict[str, Any]], plural: str, namespace: str
) -> None:
    """Show objects from Kubernetes backend."""
    if not objects:
        click.echo(f"No {plural} found.")
        return

    table = _build_table(title)
    now = datetime.now(timezone.utc)

    for item in objects:
        name, ns, creation_ts = _extract_metadata(item, namespace)
        age = _compute_age(creation_ts, now)
        status = _extract_status(item)
        table.add_row(name, ns, age, status)

    console.print(table)


def _flatten_dict(value: Dict[str, Any], parent: str) -> List[Tuple[str, Any]]:
    items: List[Tuple[str, Any]] = []
    for key, sub in value.items():
        full_key = f"{parent}.{key}" if parent else key
        items.extend(flatten_dict(sub, full_key))
    return items


def _flatten_list(value: List[Any], parent: str) -> List[Tuple[str, Any]]:
    items: List[Tuple[str, Any]] = []
    if all(isinstance(i, dict) for i in value):
        for idx, sub in enumerate(value):
            items.extend(flatten_dict(sub, f"{parent}[{idx}]"))
    else:
        items.append((parent, ", ".join(str(i) for i in value)))
    return items


def flatten_dict(data: Any, parent: str = "") -> List[Tuple[str, Any]]:
    """Flatten nested dicts/lists into dot-notation key/value pairs."""
    if isinstance(data, dict):
        return _flatten_dict(data, parent)

    if isinstance(data, list):
        return _flatten_list(data, parent)

    # Base value
    return [(parent, data)]


def render_section(title: str, content: Dict[str, Any]) -> None:
    """Render a single section of a Kubernetes object."""
    if not content:
        return

    click.secho(title, fg="green", bold=True)
    for key, value in flatten_dict(content):
        click.echo(f"  {key:25} {value}")
    click.echo()


def extract_sections(obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract metadata/spec/status sections from a Kubernetes object."""
    return {
        "Metadata": obj.get("metadata", {}),
        "Spec": obj.get("spec", {}),
        "Status": obj.get("status", {}),
    }


def describe_object(obj: Dict[str, Any]) -> None:
    """
    Render a Kubernetes object (CR or built-in) in a kubectl-describe-like table.
    """
    if not obj:
        return

    name = obj.get("metadata", {}).get("name", "<unknown>")
    namespace = obj.get("metadata", {}).get("namespace", "<default>")
    kind = obj.get("kind", "<unknown>")
    api = obj.get("apiVersion", "")

    click.secho(f"Name: {name}", fg="cyan", bold=True)
    click.secho(f"Namespace: {namespace}", fg="cyan")
    click.secho(f"Kind: {kind} | API: {api}", fg="cyan")
    click.echo()

    for section_name, content in extract_sections(obj).items():
        render_section(section_name, content)


# DNS methods


def build_dns_record_name(
    server_name: str, tenancy_name: str, hosting_location: str
) -> str:
    """
    Build a DNS hostname using the ewcloud pattern:
    <machine-name>.<tenancy-name>.<hosting-location>.ewcloud.host
    Source: https://confluence.ecmwf.int/display/EWCLOUDKB/EWC+DNS
    """
    if not all([server_name, tenancy_name, hosting_location]):
        raise ValueError(
            "All arguments (server_name, tenancy_name, hosting_location) are required."
        )

    dns_record_name = f"{server_name}.{tenancy_name}.{hosting_location}.ewcloud.host"
    _LOGGER.debug("Built DNS Record Name: %s", dns_record_name)
    return dns_record_name


def wait_for_dns_record(
    dns_record_name: str, expected_ip: str, interval: int = 60, timeout_minutes: int = 5
) -> bool:
    """
    Waits until the given dns_record_name resolves to the expected IP.
    """
    deadline = time.time() + timeout_minutes * 60
    _LOGGER.info("Waiting for %s to resolve to %s...", dns_record_name, expected_ip)
    _LOGGER.info("⏳ This could take several minutes, grab some snack meanwhile...")

    while time.time() < deadline:
        try:
            resolved_ip = socket.gethostbyname(dns_record_name)

            if resolved_ip == expected_ip:
                _LOGGER.info("Success: %s resolved to %s", dns_record_name, resolved_ip)
                return True
            else:
                _LOGGER.debug(
                    "%s currently resolves to %s (expected %s)",
                    dns_record_name,
                    resolved_ip,
                    expected_ip,
                )

        except socket.gaierror:
            _LOGGER.info(
                f"{dns_record_name} not found in DNS yet. Retrying in {interval} seconds..."
            )

        time.sleep(interval)

    _LOGGER.warning(
        "Timeout: %s did not resolve to %s within %d minutes.",
        dns_record_name,
        expected_ip,
        timeout_minutes,
    )
    return False
