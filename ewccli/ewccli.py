#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""European Weather Cloud (EWC) CLI."""

from importlib.metadata import version, PackageNotFoundError
import rich_click as click

from ewccli import __title__
from ewccli.commands.login_command import init_command, init_options

# Multiple backends
from ewccli.commands.hub.hub_command import ewc_hub_command

# Openstack backend
from ewccli.commands.infra_command import ewc_infra_command

# Crossplane backend
# from ewccli.commands.k8s_command import ewc_k8s_command
# from ewccli.commands.dns_command import ewc_dns_command
# from ewccli.commands.s3_command import ewc_s3_command

from ewccli.configuration import config as ewc_hub_config


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """European Weather Cloud (EWC) CLI."""
    pass


@cli.command(name="login", help="Initialize configuration for EWC CLI.")
@init_options
def init(
    application_credential_id: str,
    application_credential_secret: str,
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    tenant_name: str,
    region: str,
    # token: str,
):
    """Login command."""
    init_command(
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
        tenant_name=tenant_name,
        region=region,
        # token=token,
    )

def get_version():
    """
    Return the version of the installed package.

    This function first attempts to retrieve the version number using
    `importlib.metadata.version()`, which works when the package is installed
    normally (e.g., via pip). If the package is not installed and a
    `PackageNotFoundError` is raised, the version is retrieved directly from
    the package's `__version__` attribute, which supports local development
    without installation.

    Returns:
        str: The version string of the package.
    """
    try:
        return version(__title__)   # the name in pyproject.toml / setup.py
    except PackageNotFoundError:
        # fallback to direct import if running in source mode
        from ewccli import __version__
        return __version__


@cli.command(name="version", help="Show EWC CLI version.")
def version_cmd():
    """
    Display the version of the EWC CLI.

    This command reads the installed package version using `get_version()`
    and prints it to the terminal. It is useful for debugging, user support,
    and verifying correct installation of the CLI.
    """
    click.echo(get_version())


# Register subcommands
cli.add_command(ewc_hub_command)
cli.add_command(ewc_infra_command)
# cli.add_command(ewc_k8s_command)
# cli.add_command(ewc_dns_command)
# cli.add_command(ewc_s3_command)


if __name__ == "__main__":
    cli(prog_name=f"{ewc_hub_config.EWC_CLI_NAME}")
