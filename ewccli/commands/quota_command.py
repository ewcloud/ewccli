#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025, 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""EWC CLI: quota overview."""

from __future__ import annotations

from typing import Optional

import rich_click as click
from click import ClickException

from ewccli.configuration import config as ewc_hub_config
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.commands.commons import CommonBackendContext
from ewccli.commands.commons import login_options
from ewccli.commands.commons import openstack_options
from ewccli.commands.commons import openstack_error_hint
from ewccli.commands.commons_infra import show_quota_table
from ewccli.profile import ProfileStore
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)

quota_context = click.make_pass_decorator(CommonBackendContext, ensure=True)


@click.command(name="quota", help="Show Resources quota.")  # type: ignore[misc]
@quota_context  # type: ignore[misc]
@login_options
@openstack_options
def ewc_quota_command(  # noqa: CFQ002, CCR001
    ctx: click.Context,
    profile: Optional[str] = None,
    auth_url: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
) -> None:
    """Show the quota overview (CPU, RAM, block storage, floating IPs)."""
    store = ProfileStore()

    if profile:
        ctx.cli_profile = store.load(name=profile)
        _LOGGER.info(f"Using `{profile}` profile.")
    else:
        ctx.cli_profile = store.load(name=ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME)
        _LOGGER.info(f"Using `{ctx.cli_profile.profile}` profile.")

    cli_profile = ctx.cli_profile
    federee = cli_profile.federee
    region = cli_profile.region

    site_map = ewc_hub_config.EWC_CLI_SITE_MAP.get(federee)
    if site_map is None:
        raise ClickException(f"[Quota] Unknown federee '{federee}'.")

    resolved_auth_url = auth_url or site_map.get(region)
    if resolved_auth_url is None:
        raise ClickException(
            f"[Quota] Unknown region '{region}' for federee '{federee}'."
        )

    ctx.openstack_backend = OpenstackBackend(
        application_credential_id=application_credential_id
        or cli_profile.application_credential_id,
        application_credential_secret=application_credential_secret
        or cli_profile.application_credential_secret,
        auth_url=resolved_auth_url,
    )

    try:
        openstack_api = ctx.openstack_backend.connect(
            auth_url=resolved_auth_url,
            application_credential_id=application_credential_id
            or cli_profile.application_credential_id,
            application_credential_secret=application_credential_secret
            or cli_profile.application_credential_secret,
        )
    except Exception as op_error:
        raise ClickException(
            f"Could not connect to Openstack due to the following error: {op_error}"
            f"{openstack_error_hint(op_error)}"
        )

    if OpenstackBackend.get_project_id(openstack_api) is None:
        raise ClickException(
            "Could not determine the OpenStack project of the selected profile, "
            "so the quotas cannot be retrieved.\n"
            "Hint: the application credentials look invalid or expired. "
            "Check the profile in ~/.ewccli/profiles or rerun `ewc login`."
        )

    try:
        show_quota_table(ctx.openstack_backend, openstack_api)
    except ClickException:
        raise
    except Exception as quota_error:
        raise ClickException(
            f"Could not retrieve the quota information: {quota_error}"
            f"{openstack_error_hint(quota_error)}"
        )
