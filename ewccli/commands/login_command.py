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
from ewccli.configuration import LoginInput
from ewccli.configuration import config as ewc_hub_config
from ewccli.profile import ProfileData, ProfileStore
from ewccli.ssh_keys_manager import SSHKeyManager, SSHKeyError
from ewccli.enums import Federee
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


console = Console()


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
            os.getenv("OS_CLIENT_CONFIG_FILE", "~/.config/openstack/clouds.yaml")
        ).expanduser(),
        Path("/etc/openstack/clouds.yaml"),
    ]

    return any(p.exists() for p in default_paths)


def openstack_config_available() -> bool:
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
        type=click.Choice(
            [Federee.ECMWF.value, Federee.EUMETSAT.value], case_sensitive=True
        ),
        envvar="EWC_CLI_LOGIN_REGION",
        help=(
            "Cloud federee where the resources will be deployed. "
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
    - profile resolution
    - SSH key validation or generation
    - OpenStack credential resolution
    - persistence of the login profile
    """
    # 1. Resolve federee
    if not data.federee:
        federee = select_provider()
        if not federee:
            console.print("No selection made. Exiting.")
            return
    else:
        federee = data.federee

    console.print(f"Considering federee: {federee}")

    # 2. Resolve profile name
    store = ProfileStore()
    resolved_profile = store.resolve_name(data.profile, federee, data.tenant_name)

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


def _resolve_openstack_credentials(
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
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
    if openstack_config_available():
        console.print(
            "🔑 [bold green]Openstack cloud.yaml found[/bold green] – skipping credentials."
        )
        return "", ""

    if not application_credential_id:
        application_credential_id = os.getenv(
            "OS_APPLICATION_CREDENTIAL_ID"
        ) or click.prompt("Enter OpenStack Application Credential ID", hide_input=True)

    if not application_credential_secret:
        application_credential_secret = os.getenv(
            "OS_APPLICATION_CREDENTIAL_SECRET"
        ) or click.prompt(
            "Enter OpenStack Application Credential Secret", hide_input=True
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
