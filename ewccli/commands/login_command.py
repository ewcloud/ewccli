#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Login: EWC Login interaction."""

import base64
import json
import re
from typing import Optional
from pathlib import Path

import rich_click as click
from rich.console import Console
from click import ClickException

from prompt_toolkit.application import Application
from prompt_toolkit.widgets import RadioList, Box, Frame
from prompt_toolkit.layout import Layout
from prompt_toolkit.styles import Style

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import save_cli_profile
from ewccli.utils import profile_exists, update_cli_profile_credentials
from ewccli.utils import generate_ssh_keypair, check_ssh_keys_match
from ewccli.enums import Federee, Region
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


console = Console()


def _decode_jwt_subject(token: str) -> Optional[str]:
    """Extract the ``sub`` claim from a JWT without verifying its signature.

    Used to derive the OpenBao secret path (keyed by the Keycloak user id).
    Returns ``None`` if the token is malformed or has no ``sub`` claim.
    """
    try:
        payload_b64 = token.split(".")[1]
        # Add padding required by base64.urlsafe_b64decode
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except (IndexError, ValueError, UnicodeDecodeError):
        return None

    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None


def kubeconfig_available():
    """Verify if kubeconfig is available."""
    try:
        from kubernetes import config as k8s_config
        from kubernetes.config.config_exception import (  # noqa: N813
            ConfigException as kubernetes_config_exception,
        )

        k8s_config.load_kube_config()
        return True
    except kubernetes_config_exception as e:
        _LOGGER.warning(
            f"⚠️ Kubeconfig not found: {e}\n"
            "You could set KUBECONFIG=/path/to/your/kubeconfig or continue below using the token"
        )
        return False
    except Exception as e:
        _LOGGER.warning(f"⚠️ Kubeconfig not found: {e}")
        return False


def validate_tenant_name(ctx, param, value):
    """Validate tenant name."""
    if not value:
        return value
    pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
    if not re.match(pattern, value):
        raise click.BadParameter(
            "Config name must be exactly 3 alphanumeric parts separated by dashes (e.g. thisis-my-tenancy)."
        )
    return value


def validate_region(ctx, param, value):
    federee = ctx.params.get("federee")
    if federee is None or value is None:
        return value

    allowed = ewc_hub_config.allowed_regions(Federee(federee))

    if value not in allowed:
        raise click.BadParameter(
            f"Region '{value}' is not valid for federee '{federee}'. "
            f"Allowed: {', '.join(allowed)}"
        )

    return value


def init_options(func):
    """Login options for the CLI login command."""
    func = click.option(
        "--tenant-name",
        envvar="EWC_CLI_LOGIN_TENANT_NAME",
        required=False,
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
    func = click.option(
        "--no-browser",
        is_flag=True,
        default=False,
        help=(
            "Print the login URL instead of opening a browser. "
            "Useful for SSH sessions or headless environments."
        ),
    )(func)
    return func


def select_federee():
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


def select_region(federee: str):
    """Select region based on the chosen federee."""

    # Load allowed regions from your config
    allowed = ewc_hub_config.allowed_regions(federee)

    # Convert to RadioList format: (display, value)
    choices = [(r, r) for r in allowed]

    radio_list = RadioList(choices)
    kb = radio_list.control.key_bindings

    @kb.add("enter")
    def _(event):
        index = radio_list._selected_index
        selected_value = radio_list.values[index][1]
        event.app.exit(result=selected_value)

    @kb.add("c-c")
    @kb.add("c-q")
    def _(event):
        event.app.exit(None)

    root_container = Box(Frame(radio_list, title=f"Select Region for {federee}"), padding=1)
    layout = Layout(root_container)

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=True,
        style=Style.from_dict({"frame.label": "bold"}),
    )

    selected = app.run()
    return selected


def check_and_generate_ssh_keys(
    ssh_public_key_path: Optional[str],
    ssh_private_key_path: Optional[str],
    resolved_profile: str
):
    """Check for SSH keys, prompt to generate if missing"""
    if not ssh_private_key_path:
        ssh_private_key_path = ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH / f"{resolved_profile}_id_rsa"

    if not ssh_public_key_path:
        ssh_public_key_path = ewc_hub_config.EWC_CLI_HUB_SSH_REPO_PATH / f"{resolved_profile}_id_rsa.pub"

    private_exists = Path(ssh_private_key_path).exists()
    public_exists = Path(ssh_public_key_path).exists()

    if private_exists and public_exists:
        # case 1: both exist
        console.print(
            "Using the following path for the SSH keypair:"
            f"\nSSH public key path: {ssh_public_key_path}"
            f"\nSSH private key path: {ssh_private_key_path}\n"
        )
        console.print("SSH key pair exists, checking consistency...")

        is_matching = check_ssh_keys_match(
            ssh_private_key_path=ssh_private_key_path,
            ssh_public_key_path=ssh_public_key_path
        )

        if not is_matching:
            raise ClickException(
                "SSH keys provided are not a correct keypair:"
                f"\nSSH public key path: {ssh_public_key_path}"
                f"\nSSH private key path: {ssh_private_key_path}"
                "\nMake sure either you pass correct SSH keypair in the EWC login command through the following flags `--ssh-private-key-path` and `--ssh-public-key-path`"
                "or let the `ewc login` command create them for you. Exiting."
            )
        else:
            click.secho("SSH private and public keys are matching! Continuing...", fg="green")

        return ssh_private_key_path, ssh_public_key_path

    elif not private_exists and not public_exists:
        # case 2: neither exists
        console.print(
            "SSH keypair is missing:"
            f"\nSSH public key path: {ssh_public_key_path}"
            f"\nSSH private key path: {ssh_private_key_path}\n"
        )

        if click.confirm("Do you want to generate a new SSH key pair?", default=False):
            ssh_custom_private_key_path, ssh_custom_public_key_path = generate_ssh_keypair(
                resolved_profile=resolved_profile
            )
            return ssh_custom_private_key_path, ssh_custom_public_key_path
        else:
            raise ClickException(
                "SSH key generation skipped but SSH keys are mandatory to deploy VMs or hub items."
                " Make sure either you pass SSH keys in the EWC login command through the following flags `--ssh-private-key-path` and `--ssh-public-key-path`"
                "or let the `ewc login` command create them for you. Exiting."
            )

    else:
        # case 3: exactly one exists
        if private_exists and not public_exists:
            key_exists = "public"
            key_path = ssh_public_key_path

        if not private_exists and public_exists:
            key_exists = "private"
            key_path = ssh_private_key_path

        raise ClickException(
            f"SSH {key_exists} key is missing at: {key_path}."
            " Make sure the keypair is passed!"
            " You can pass SSH keys in the EWC login command through the following flags `--ssh-private-key-path` or `--ssh-public-key-path`"
            "or let the `ewc login` command create them for you. Exiting."
        )


def _fetch_openbao_credentials(access_token: str, profile_name: str):
    """Login to OpenBao with the Keycloak access token and read the user secret.

    Returns a dict with keys: ``kubeconfig``, ``application_credential_id``,
    ``application_credential_secret``. The kubeconfig (if any) is written to
    ``~/.ewccli/kubeconfigs/<profile>.yaml`` and its path is returned in
    place of the raw content.
    """
    from ewccli.backends.openbao.openbao_client import OpenBaoClient, OpenBaoError

    user_id = _decode_jwt_subject(access_token)
    if not user_id:
        raise ClickException(
            "Could not extract user id (sub claim) from the Keycloak access token. "
            "Please run 'ewc login' again."
        )

    client = OpenBaoClient(
        url=ewc_hub_config.EWC_CLI_OPENBAO_URL,
        namespace=ewc_hub_config.EWC_CLI_OPENBAO_NAMESPACE,
        role=ewc_hub_config.EWC_CLI_OPENBAO_OIDC_ROLE,
        kv_mount=ewc_hub_config.EWC_CLI_OPENBAO_KV_MOUNT,
        access_token=access_token,
    )

    try:
        client.login()
        secret_data = client.read_secret(user_id)
    except OpenBaoError as e:
        raise ClickException(
            f"Failed to retrieve credentials from OpenBao: {e}"
        ) from e

    kubeconfig_content = secret_data.get("kubeconfig")
    kubeconfig_path = None
    if kubeconfig_content:
        kubeconfig_dir = ewc_hub_config.EWC_CLI_KUBECONFIG_PATH
        kubeconfig_dir.mkdir(parents=True, exist_ok=True)
        kubeconfig_path = kubeconfig_dir / f"{profile_name}.yaml"
        kubeconfig_path.write_text(kubeconfig_content)
        _LOGGER.info(f"Kubeconfig saved to {kubeconfig_path}")

    return {
        "kubeconfig_path": str(kubeconfig_path) if kubeconfig_path else None,
        "application_credential_id": secret_data.get("application_credential_id"),
        "application_credential_secret": secret_data.get("application_credential_secret"),
    }


def init_command(
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    tenant_name: str,
    federee: str,
    region: str,
    profile: str = None,
    no_browser: bool = False,
):
    """EWC CLI Login — Keycloak OIDC → OpenBao → downstream credentials.

    No Keycloak tokens are persisted. The profile stores only the downstream
    credentials (app creds, kubeconfig path, federee, region, tenant_name,
    SSH keys).
    """
    from ewccli.backends.keycloak.keycloak_backend import keycloak_login
    from ewccli.utils import load_cli_profile

    # 1. Resolve profile name (use default if not given)
    resolved_profile = profile or ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME
    profiles_file_path = ewc_hub_config.EWC_CLI_PROFILES_PATH

    # 2. Check if the profile already exists (re-login)
    profile_already_exists = profile_exists(resolved_profile, profiles_file_path)

    if profile_already_exists:
        existing_profile = load_cli_profile(
            profile=resolved_profile, profiles_file_path=profiles_file_path
        )
        if not federee:
            federee = existing_profile.get("federee")
        if not region:
            region = existing_profile.get("region")
        if not tenant_name:
            tenant_name = existing_profile.get("tenant_name")
        console.print(
            f"Using existing profile '[bold cyan]{resolved_profile}[/bold cyan]' — refreshing credentials."
        )

    # 3. Keycloak OIDC login → ephemeral access token
    kc_result = keycloak_login(
        config=ewc_hub_config,
        open_browser=not no_browser,
        federee=federee,
    )

    # 4. Decode JWT to extract user_id (sub claim) — needed for OpenBao path
    # 5. OpenBao OIDC login + read secret
    # 6. Extract kubeconfig → save to ~/.ewccli/kubeconfigs/<profile>.yaml
    #    Extract app credential id + secret
    bao_creds = _fetch_openbao_credentials(
        access_token=kc_result.access_token,
        profile_name=resolved_profile,
    )
    application_credential_id = bao_creds.get("application_credential_id") or ""
    application_credential_secret = bao_creds.get("application_credential_secret") or ""
    kubeconfig_path = bao_creds.get("kubeconfig_path")

    # 7. Interactive prompts for federee/region/tenant_name (new profiles only)
    if not profile_already_exists:
        if not federee:
            federee = select_federee()
            if not federee:
                console.print("No federee selection made. Exiting.")
                return

        console.print(f"Considering federee: {federee}")

        if not region:
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

        if not tenant_name:
            tenant_name = click.prompt("Tenant name")

    # 8. SSH keys (unchanged)
    ssh_private_key_path_to_save, ssh_public_key_path_to_save = check_and_generate_ssh_keys(
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
        resolved_profile=resolved_profile,
    )

    # 9. Save profile
    if profile_already_exists:
        update_cli_profile_credentials(
            profile=resolved_profile,
            application_credential_id=application_credential_id or None,
            application_credential_secret=application_credential_secret or None,
            kubeconfig_path=kubeconfig_path,
            profiles_file_path=profiles_file_path,
        )
    else:
        save_cli_profile(
            federee=federee,
            region=region,
            tenant_name=tenant_name,
            ssh_private_key_path_to_save=ssh_private_key_path_to_save,
            ssh_public_key_path_to_save=ssh_public_key_path_to_save,
            profile=resolved_profile,
            application_credential_id=application_credential_id,
            application_credential_secret=application_credential_secret,
            kubeconfig_path=kubeconfig_path,
            profiles_file_path=profiles_file_path,
        )

    console.print(
        f"✅ Profile '[bold cyan]{resolved_profile}[/bold cyan]' saved "
        f"in the following file {ewc_hub_config.EWC_CLI_PROFILES_PATH}"
    )
