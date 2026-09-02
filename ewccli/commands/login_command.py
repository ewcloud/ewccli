#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Login: EWC Login interaction."""

import os
import re
from typing import Optional
from pathlib import Path
from typing import Callable, Any
from typing import NoReturn

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from click import ClickException

from prompt_toolkit.key_binding import KeyPressEvent
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
from pydantic import BaseModel

from ewccli.configuration import config as ewc_hub_config
from ewccli.profile import ProfileData, ProfileStore
from ewccli.ssh_keys_manager import SSHKeyManager, SSHKeyError
from ewccli.enums import Federee, Region
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)
_DEFAULT_OPENSTACK_CLOUD_CONFIG_PATH = "~/.config/openstack/clouds.yaml"

console = Console()


class LoginInput(BaseModel):  # type: ignore[misc]
    """
    Raw login input provided by the user before resolution.
    """

    tenant_name: str
    federee: str
    region: str

    application_credential_id: Optional[str] = None
    application_credential_secret: Optional[str] = None

    ssh_public_key_path: Optional[str] = None
    ssh_private_key_path: Optional[str] = None

    profile: Optional[str] = None


def kubeconfig_available() -> bool:
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


def cloud_yaml_exists() -> bool:
    """Check if OpenStack clouds.yaml file exists."""
    # Default OpenStack config paths (can vary by environment)
    default_paths = [
        Path(
            os.getenv("OS_CLIENT_CONFIG_FILE", _DEFAULT_OPENSTACK_CLOUD_CONFIG_PATH)
        ).expanduser(),
        Path("/etc/openstack/clouds.yaml"),
    ]

    return any(p.exists() for p in default_paths)


def openstack_config_available(cloud_name: str = "openstack") -> bool:  # noqa: CFQ004
    """Verify if OpenStack cloud config is available."""
    try:
        os_config = OpenStackConfig()
        if cloud_yaml_exists():
            cloud_names = os_config.get_cloud_names()

            if cloud_name not in cloud_names:
                _LOGGER.warning(
                    "OpenStack cloud config found at '~/.config/openstack/clouds.yaml'\n"
                    f"But no clouds match the cloud name '{cloud_name}'\n"
                    f"{cloud_names}\n\n"
                    "You can choose the cloud you want with the --cloud-name flag.\n"
                    "You can set the config path with the environment variable:\n"
                    "  OS_CLIENT_CONFIG_FILE=/path/to/clouds.yaml\n"
                    "Alternatively, provide your credentials using:\n"
                    "  OS_APPLICATION_CREDENTIAL_ID and OS_APPLICATION_CREDENTIAL_SECRET\n"
                    "Or continue below to enter them manually."
                )
                return False
            return True
        else:
            _LOGGER.warning(
                "⚠️ OpenStack cloud config not found at '~/.config/openstack/clouds.yaml'\n"
                "You can set the config path with the environment variable:\n"
                "  OS_CLIENT_CONFIG_FILE=/path/to/clouds.yaml\n"
                "Alternatively, provide your credentials using:\n"
                "  OS_APPLICATION_CREDENTIAL_ID and OS_APPLICATION_CREDENTIAL_SECRET\n"
                "Or continue below to enter them manually."
            )
            return False
    except openstack_config_exception as e:
        _LOGGER.warning(
            f"⚠️ OpenStack cloud config not found: {e}\n"
            "You can also set the config path with `OS_CLIENT_CONFIG_FILE=/path/to/clouds.yaml` or continue below"
        )
        return False


def validate_tenant_name(
    ctx: click.Context,
    param: click.Parameter,
    value: str,
) -> str:
    """Validate tenant name."""
    pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
    if not re.match(pattern, value):
        raise click.BadParameter(
            "Config name must be exactly 3 alphanumeric parts separated by dashes (e.g. thisis-my-tenancy)."
        )
    return value


def validate_region(
    ctx: click.Context, param: click.Parameter, value: Optional[str]
) -> str | None:
    """Validate region."""
    federee = ctx.params.get("federee")
    if federee is None or value is None:
        return value

    allowed = ewc_hub_config.allowed_regions(federee)

    if value not in allowed:
        raise click.BadParameter(
            f"Region '{value}' is not valid for federee '{federee}'. "
            f"Allowed: {', '.join(allowed)}"
        )

    return value


def init_options(func: Callable[..., Any]) -> Callable[..., Any]:
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
        "--federee",
        type=click.Choice([r.value for r in Federee], case_sensitive=True),
        required=False,
        envvar="EWC_CLI_LOGIN_FEDEREE",
        help=(
            "Cloud federee where the resources will be deployed. "
            "You can also set this using the EWC_CLI_LOGIN_FEDEREE environment variable. "
            "If not provided, you'll be prompted to choose."
        ),
    )(func)
    func = click.option(
        "--region",
        type=click.Choice([r.value for r in Region], case_sensitive=True),
        required=False,
        callback=validate_region,
        envvar="EWC_CLI_LOGIN_REGION",
        help=(
            "Region to deploy resources. Allowed values depend on the federee."
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
            f"or if a clouds.yaml config is found at '{_DEFAULT_OPENSTACK_CLOUD_CONFIG_PATH}' "
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
            f"or if a clouds.yaml config is found at '{_DEFAULT_OPENSTACK_CLOUD_CONFIG_PATH}' "
            "or at the path specified by OS_CLIENT_CONFIG_FILE."
        ),
    )(func)
    func = click.option(
        "--cloud-name",
        required=False,
        default="openstack",
        show_default=True,
        help=(
            "OpenStack cloud name from OpenStack cloud config"
            f" file available at '{_DEFAULT_OPENSTACK_CLOUD_CONFIG_PATH}' "
            "or at the path specified by OS_CLIENT_CONFIG_FILE."
            " This flag is ignored if the cloud config file is not present."
        ),
    )(func)
    func = click.option(
        "--ssh-public-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PUBLIC_KEY_PATH",
        type=str,
        show_default=True,
        help="Path to SSH public key.",
    )(func)
    func = click.option(
        "--ssh-private-key-path",
        required=False,
        envvar="EWC_CLI_SSH_PRIVATE_KEY_PATH",
        type=str,
        show_default=True,
        help="Path to SSH private key.",
    )(func)
    func = click.option(
        "--profile",
        envvar="EWC_CLI_LOGIN_PROFILE",
        required=False,
        help="EWC CLI profile name",
    )(func)
    return func


def select_provider() -> Any:
    """Select provider."""
    choices = [
        ("EUMETSAT", "EUMETSAT"),
        ("ECMWF", "ECMWF"),
    ]

    radio_list = RadioList(choices)

    # Use the widget's own default key bindings
    kb = radio_list.control.key_bindings

    @kb.add("enter")  # type: ignore[misc]
    def _(event: KeyPressEvent) -> None:
        index = radio_list._selected_index
        selected_value = radio_list.values[index][
            1
        ]  # values is list of tuples (display, value)
        event.app.exit(result=selected_value)

    # Add quit keys as well
    @kb.add("c-c")  # type: ignore[misc]
    @kb.add("c-q")  # type: ignore[misc]
    def _(event: KeyPressEvent) -> None:
        event.app.exit(None)

    root_container = Box(Frame(radio_list, title="Select Federee"), padding=1)
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


def select_region(federee: str) -> str:
    """Select region based on the chosen federee."""

    # Load allowed regions from your config
    allowed = ewc_hub_config.allowed_regions(federee)

    # Convert to RadioList format: (display, value)
    choices = [(r, r) for r in allowed]

    radio_list = RadioList(choices)
    kb = radio_list.control.key_bindings

    @kb.add("enter")  # type: ignore[misc]
    def _(event: click.Event) -> None:
        index = radio_list._selected_index
        selected_value = radio_list.values[index][1]
        event.app.exit(result=selected_value)

    @kb.add("c-c")  # type: ignore[misc]
    @kb.add("c-q")  # type: ignore[misc]
    def _(event: click.Event) -> None:
        event.app.exit(None)

    root_container = Box(
        Frame(radio_list, title=f"Select Region for {federee}"), padding=1
    )
    layout = Layout(root_container)

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=True,
        style=Style.from_dict({"frame.label": "bold"}),
    )

    selected: str = app.run()
    return selected


def check_and_generate_ssh_keys(
    ssh_public_key_path: Optional[str],
    ssh_private_key_path: Optional[str],
    resolved_profile: str,
) -> tuple[str, str]:
    """
    Ensure SSH keys exist and match, or generate them if missing.
    """
    manager = SSHKeyManager()
    priv, pub = _resolve_default_paths(
        ssh_public_key_path,
        ssh_private_key_path,
        resolved_profile,
    )

    private_exists = priv.exists()
    public_exists = pub.exists()

    if private_exists and public_exists:
        return _handle_existing_keys(manager, priv, pub)

    if not private_exists and not public_exists:
        return _handle_missing_keys(manager, priv, pub, resolved_profile)

    return _handle_partial_keys(priv, pub)


def _handle_existing_keys(
    manager: SSHKeyManager, priv: Path, pub: Path
) -> tuple[str, str]:
    """
    Validate an existing SSH keypair and return their paths.
    """
    console.print(
        Panel(
            f"Using existing SSH keypair:\n"
            f"[green]Public:[/green]  {pub}\n"
            f"[green]Private:[/green] {priv}",
            title="SSH Keys Found",
            style="cyan",
        )
    )

    console.print("Checking SSH keypair consistency...")

    try:
        manager.keys_match(priv, pub)
    except SSHKeyError as exc:
        raise ClickException(
            f"SSH keys are invalid or mismatched:\n{exc}\n"
            "Provide a correct keypair or let `ewc login` generate one."
        )

    console.print("[green]SSH keypair is valid. Continuing...[/green]")
    return str(priv), str(pub)


def _handle_missing_keys(
    manager: SSHKeyManager, priv: Path, pub: Path, resolved_profile: str
) -> tuple[str, str]:
    """
    Handle the case where no SSH keys exist.
    """
    console.print(
        Panel(
            f"SSH keypair not found:\nPublic:  {pub}\nPrivate: {priv}",
            title="SSH Keys Missing",
            style="yellow",
        )
    )

    if click.confirm("Generate a new SSH keypair?", default=False):
        new_priv, new_pub = manager.generate_keypair(resolved_profile)
        return str(new_priv), str(new_pub)

    raise ClickException(
        "SSH keys are required. Provide them via:\n"
        "  --ssh-private-key-path\n"
        "  --ssh-public-key-path\n"
        "or allow `ewc login` to generate them."
    )


def _handle_partial_keys(priv: Path, pub: Path) -> NoReturn:
    """
    Raise an error when only one of the SSH keys exists.
    """
    if priv.exists() and not pub.exists():
        missing = "public"
        missing_path = pub
    else:
        missing = "private"
        missing_path = priv

    raise ClickException(
        f"SSH {missing} key is missing at: {missing_path}\n"
        "Provide a complete keypair or let `ewc login` generate one."
    )


def _resolve_default_paths(
    ssh_public_key_path: Optional[str],
    ssh_private_key_path: Optional[str],
    resolved_profile: str,
) -> tuple[Path, Path]:
    """
    Resolve SSH key paths, falling back to profile-based defaults.
    """
    if not ssh_private_key_path:
        ssh_private_key_path = str(
            ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH / f"{resolved_profile}_id_rsa"
        )

    if not ssh_public_key_path:
        ssh_public_key_path = str(
            ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH / f"{resolved_profile}_id_rsa.pub"
        )

    return (
        Path(ssh_private_key_path).expanduser(),
        Path(ssh_public_key_path).expanduser(),
    )


def init_command(data: LoginInput) -> None:
    """
    Initialize an EWC CLI login session.

    This orchestrates:
    - federee selection
    - region selection
    - profile resolution
    - SSH key validation or generation
    - OpenStack credential resolution
    - persistence of the login profile
    """
    # 1.1 Resolve federee
    if not data.federee:
        federee = select_provider()
        if not federee:
            console.print("No federee selection made. Exiting.")
            return
    else:
        federee = data.federee

    console.print(f"Considering federee: {federee}")

    # 1.2 Resolve region
    region = data.region  # always initialize

    if not region:
        # If --region is not passed, ask interactively
        region = select_region(federee=federee)

    if not region:
        console.print("No region selection made. Exiting.")
        return

    allowed_regions = ewc_hub_config.allowed_regions(federee)

    if region not in allowed_regions:
        raise click.BadParameter(
            f"Region '{region}' is not valid for federee '{federee}'. "
            f"Allowed: {', '.join(allowed_regions)}"
        )

    console.print(f"Considering region: {region}\n")

    # 2. Resolve profile name
    store = ProfileStore()
    resolved_profile = store.resolve_name(
        profile=data.profile,
        federee=federee,
        tenant_name=data.tenant_name,
        region=region,
    )

    # 3. Ensure profile does not already exist
    _ensure_profile_not_exists(store, resolved_profile)

    # 4. Resolve SSH keys
    priv_path, pub_path = _resolve_ssh_keys(
        ssh_public_key_path=data.ssh_public_key_path,
        ssh_private_key_path=data.ssh_private_key_path,
        resolved_profile=resolved_profile,
    )

    # 5. Resolve OpenStack credentials
    application_credential_id, application_credential_secret = (
        _resolve_openstack_credentials(
            data.application_credential_id,
            data.application_credential_secret,
        )
    )

    # TODO: token not available in the profile
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

    # 6. Build the Pydantic model
    profile_data = ProfileData(
        federee=federee,
        tenant_name=data.tenant_name,
        region=data.region,
        profile=resolved_profile,
        ssh_private_key_path_to_save=str(priv_path),
        ssh_public_key_path_to_save=str(pub_path),
        # token=None,
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
    )

    # 7. Save profile
    store.save_default(profile_data)
    store.save(profile_data)

    console.print(
        f"✅ Profile '[bold cyan]{resolved_profile}[/bold cyan]' saved in {store.path}"
    )


def _resolve_ssh_keys(
    ssh_public_key_path: Optional[str],
    ssh_private_key_path: Optional[str],
    resolved_profile: str,
) -> tuple[str, str]:
    """
    Resolve SSH keypair for the login flow.

    Delegates all SSH key validation and generation logic to
    `check_and_generate_ssh_keys`, which uses SSHKeyManager internally.

    Returns
    -------
    tuple[str, str]
        The resolved private and public SSH key paths.
    """
    return check_and_generate_ssh_keys(
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
        resolved_profile=resolved_profile,
    )


def _resolve_openstack_credentials(  # noqa: CCR001
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    cloud_name: str = "openstack",
) -> tuple[str, str]:
    """
    Resolve OpenStack application credentials.

    If a valid OpenStack clouds.yaml is detected, credentials are skipped.
    Otherwise, missing values are retrieved from environment variables
    or prompted interactively.

    Returns
    -------
    tuple[str, str]
        The resolved (ID, secret) pair.
    """
    if openstack_config_available(cloud_name=cloud_name):
        os_cloud_config_file_path = os.getenv("OS_CLIENT_CONFIG_FILE")

        os_cloud_config_selected_path = (
            os_cloud_config_file_path
            if os_cloud_config_file_path
            else _DEFAULT_OPENSTACK_CLOUD_CONFIG_PATH
        )
        console.print(
            f"🔑 [bold green]Openstack cloud config found at {os_cloud_config_selected_path} [/bold green]"
            " – skipping Openstack ID and secret requirement prompt."
        )

        # default to ~/.config/openstack/clouds.yaml, to change use OS_CLIENT_CONFIG_FILE
        config = OpenStackConfig()
        cloud = config.get_one(cloud=cloud_name)

        cloud_config = cloud.config.get("auth")
        application_credential_id = cloud_config.get("application_credential_id")
        application_credential_secret = cloud_config.get(
            "application_credential_secret"
        )

        return application_credential_id, application_credential_secret

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

        return application_credential_id, application_credential_secret

    else:
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

        return application_credential_id, application_credential_secret


def _ensure_profile_not_exists(store: ProfileStore, resolved_profile: str) -> None:
    """
    Ensure that a profile with the given name does not already exist.

    Raises
    ------
    click.Abort
        If the profile already exists.
    """
    if store.exists(resolved_profile):
        click.secho(
            f"❌ Profile '{resolved_profile}' already exists in {store.path}",
            fg="red",
            bold=True,
        )
        click.secho(
            "Use a different profile name or delete the existing profile first.",
            fg="yellow",
        )
        raise click.Abort()
