#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Login: EWC Login interaction."""

from typing import Optional
from pathlib import Path

import rich_click as click
from rich.console import Console
from click import ClickException

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import save_cli_profile
from ewccli.utils import profile_exists, update_cli_profile_credentials
from ewccli.utils import generate_ssh_keypair, check_ssh_keys_match
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


console = Console()


def init_options(func):
    """Login options for the CLI login command."""
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


def init_command(
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    profile: str = None,
    no_browser: bool = False,
):
    """EWC CLI Login — kubelogin -> KKP API -> OIDC kubeconfig.

    Flow: kubelogin obtains a kubermatic-audience token (browser auth,
    cached ~2h), that token authenticates to the KKP API which returns
    an OIDC kubeconfig, the kubeconfig is post-processed (auth-provider
    -> exec plugin), saved, and the SSH tunnel + /etc/hosts entry are
    set up for apiserver reachability.

    No OIDC tokens are persisted. The profile stores only the kubeconfig
    path and SSH keys.
    """
    from ewccli.backends.kkp.kubelogin import get_kkp_token
    from ewccli.backends.kkp.kkp_client import KKPClient, KKPError
    from ewccli.backends.kkp.kubeconfig_processor import (
        patch_kubeconfig,
        extract_hostname,
    )
    from ewccli.backends.kkp.network import (
        ensure_tunnel,
        ensure_hosts_entry,
        ensure_kubelogin,
    )

    # 1. Resolve profile name (use default if not given)
    resolved_profile = profile or ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME
    profiles_file_path = ewc_hub_config.EWC_CLI_PROFILES_PATH
    profile_already_exists = profile_exists(resolved_profile, profiles_file_path)

    if profile_already_exists:
        console.print(
            f"Using existing profile '[bold cyan]{resolved_profile}[/bold cyan]' — refreshing kubeconfig."
        )

    # 2. Ensure kubelogin binary
    ensure_kubelogin()

    # 3. Get KKP API token (browser auth, cached ~2h)
    token = get_kkp_token(
        issuer=ewc_hub_config.EWC_CLI_KKP_DEX_ISSUER,
        client_id=ewc_hub_config.EWC_CLI_KKP_CLIENT_ID,
        client_secret=ewc_hub_config.EWC_CLI_KKP_CLIENT_SECRET,
    )

    # 4. Fetch raw kubeconfig from KKP API
    project_id = ewc_hub_config.EWC_CLI_KKP_PROJECT_ID
    cluster_id = ewc_hub_config.EWC_CLI_KKP_CLUSTER_ID
    if not project_id or not cluster_id:
        raise ClickException(
            "EWC_CLI_KKP_PROJECT_ID and EWC_CLI_KKP_CLUSTER_ID must be set. "
            "Export them or add to your shell profile."
        )

    client = KKPClient(
        api_url=ewc_hub_config.EWC_CLI_KKP_API_URL,
        token=token,
    )
    try:
        raw = client.get_oidc_kubeconfig(
            project_id=project_id,
            cluster_id=cluster_id,
        )
    except KKPError as e:
        raise ClickException(f"Failed to fetch kubeconfig from KKP API: {e}") from e

    # 5. Post-process: auth-provider -> exec
    patched = patch_kubeconfig(raw)

    # 6. Save kubeconfig
    kc_dir = ewc_hub_config.EWC_CLI_KUBECONFIG_PATH
    kc_dir.mkdir(parents=True, exist_ok=True)
    kc_path = kc_dir / f"{resolved_profile}.yaml"
    kc_path.write_text(patched)
    _LOGGER.info(f"Kubeconfig saved to {kc_path}")

    # 7. Network setup (tunnel + /etc/hosts)
    hostname = extract_hostname(patched)
    if hostname:
        ensure_tunnel(
            jump_host=ewc_hub_config.EWC_CLI_SSH_JUMP,
            tunnel_host=ewc_hub_config.EWC_CLI_TUNNEL_HOST,
            apiserver_ip=ewc_hub_config.EWC_CLI_APISERVER_IP,
        )
        ensure_hosts_entry(hostname)

    # 8. SSH keys (still needed for hub/infra)
    ssh_private_key_path_to_save, ssh_public_key_path_to_save = check_and_generate_ssh_keys(
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
        resolved_profile=resolved_profile,
    )

    # 9. Save profile
    if profile_already_exists:
        update_cli_profile_credentials(
            profile=resolved_profile,
            kubeconfig_path=str(kc_path),
            profiles_file_path=profiles_file_path,
        )
    else:
        save_cli_profile(
            federee="",  # ponytail: kept for backward compat, empty for k8s-only
            region="",
            tenant_name="",
            ssh_private_key_path_to_save=ssh_private_key_path_to_save,
            ssh_public_key_path_to_save=ssh_public_key_path_to_save,
            profile=resolved_profile,
            kubeconfig_path=str(kc_path),
            profiles_file_path=profiles_file_path,
        )

    console.print(
        f"✅ Profile '[bold cyan]{resolved_profile}[/bold cyan]' saved. "
        f"Kubeconfig: {kc_path}"
    )
