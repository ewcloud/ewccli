#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Hub: EWC Hub interaction."""

import os
import ast
import re
from typing import Optional, List, Dict, Any

import rich_click as click
from rich.console import Console
from click import ClickException
from click import get_current_context

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import download_items
from ewccli.commands.hub.hub_utils import verify_item_is_deployable
from ewccli.commands.hub.hub_utils import extract_annotations
from ewccli.commands.hub.hub_utils import prepare_missing_inputs_error_message
from ewccli.commands.commons import openstack_options
from ewccli.commands.commons import ssh_options
from ewccli.commands.commons import ssh_options_encoded
from ewccli.commands.commons import openstack_optional_options
from ewccli.commands.commons import list_items_table
from ewccli.commands.commons import show_item_table
from ewccli.commands.commons import validate_config_name
from ewccli.commands.commons import split_config_name
from ewccli.commands.commons import default_username
from ewccli.commands.commons import HubContext
from ewccli.commands.commons import CommonContext
from ewccli.commands.commons_infra import deploy_server
from ewccli.commands.hub.hub_backends import git_clone_item
from ewccli.commands.hub.hub_backends import run_ansible_playbook_item
from ewccli.commands.hub.hub_backends import get_hub_item_env_variable_value
from ewccli.commands.hub.hub_backends import HUB_ENV_VARIABLES_MAP
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.enums import HubItemTechnologyAnnotation
from ewccli.enums import HubItemCategoryAnnotation
from ewccli.enums import HubItemCLIKeys
from ewccli.logger import get_logger
from ewccli.utils import load_cli_config

_LOGGER = get_logger(__name__)

console = Console()

hub_context = click.make_pass_decorator(HubContext, ensure=True)
common_context = click.make_pass_decorator(CommonContext, ensure=True)


@click.group(name="hub")
def ewc_hub_command():
    """EWC Community Hub commands group."""
    download_items(force=ewc_hub_config.EWC_CLI_HUB_DOWNLOAD_ITEMS)


def _extract_item_inputs_class(ctx, item):  # noqa CCR001
    if item not in [i for i, v in ctx.items.items()]:
        list_items_table(hub_items=ctx.items)
        raise ClickException(
            f"{item} is not available in the EWC Hub. Please check the list above."
        )

    item_info = ctx.items[item]

    is_item_deployable = verify_item_is_deployable(item_info)
    if not is_item_deployable:
        raise ClickException("❌ Item is not deployable. Exiting.")

    item_info_ewccli = item_info.get(HubItemCLIKeys.ROOT.value, {})
    all_item_inputs = item_info_ewccli.get(HubItemCLIKeys.INPUTS.value, [])
    default_inputs = []
    required_inputs = []

    if not all_item_inputs:
        return item_info, required_inputs, default_inputs

    # if no inputs exist for the item, no inputs are requested from the user
    # and the parameter remains not required
    for item_input in all_item_inputs:
        if (
            item_input.get("default")
            or item_input.get("default") == False  # noqa E712
            or item_input.get("name", "") in HUB_ENV_VARIABLES_MAP
        ):
            default_inputs.append(item_input)
        else:
            required_inputs.append(item_input)

    ctx = get_current_context()  # <-- Get Click Context

    ctx.command.params[3].type = click.Choice(required_inputs)
    ctx.command.params[3].required = True
    ctx.command.params[3].nargs = len(required_inputs)

    return item_info, required_inputs, default_inputs


def _validate_item_inputs_format(ctx, param, values):
    if not values:
        return {}

    result = {}
    key_value_pattern = re.compile(
        r"^[^=]+=[^=]+$"
    )  # Only <key>=<value> format allowed

    for item in values:
        item = item.strip()

        if not key_value_pattern.match(item):
            raise click.BadParameter(
                f"Invalid format '{item}'. Expected format: <key>=<value>"
            )

        key, val = item.split("=", 1)
        key = key.strip()
        val = val.strip()

        # Fix: Always try to parse the value using literal_eval
        try:
            parsed_val = ast.literal_eval(val)
        except (ValueError, SyntaxError):
            parsed_val = (
                val  # fallback to string if it's not parseable (like a bare string)
            )

        result[key] = parsed_val

    return result


def _validate_required_inputs(
    parsed_inputs: Optional[Dict[str, str]], required_item_inputs: List[dict]
) -> Optional[List[Any]]:
    """
    Verify that all required inputs are provided.

    :param parsed_inputs: dict of user-provided inputs
    :param required_item_inputs: list of dicts defining required inputs
    :return: list of missing required input names
    """
    if not required_item_inputs:
        return []

    # Extract required keys from the required_item_inputs definitions
    required_keys = [item_input.get("name") for item_input in required_item_inputs]

    # Determine which required keys are missing from user inputs
    missing_keys = [
        key for key in required_keys if not parsed_inputs or key not in parsed_inputs
    ]

    return missing_keys


def _validate_item_input_types(  # noqa: CCR001, C901
    parsed_inputs: Optional[dict], schema: Optional[list]
) -> str:
    if not schema or not parsed_inputs:
        return ""

    type_errors = []
    expected_types = {entry.get("name"): entry.get("type") for entry in schema}

    for key, value in parsed_inputs.items():
        expected = expected_types.get(key)

        if not expected:
            continue  # skip unknown keys

        if expected == "str":
            if not isinstance(value, str):
                type_errors.append(f"'{key}' must be a string.")

        elif expected == "int":
            if not isinstance(value, int):
                type_errors.append(f"'{key}' must be an integer.")

        elif expected == "bool":
            if not isinstance(value, bool):
                type_errors.append(f"'{key}' must be a boolean (true/false).")

        elif expected == "dict":
            if not isinstance(value, dict):
                type_errors.append(f"'{key}' must be a dictionary.")

        elif expected == "List[str]":
            if not isinstance(value, list) or not all(
                isinstance(i, str) for i in value
            ):
                type_errors.append(
                    f"'{key}' must be a list of strings."
                    " To pass a list (e.g. List[str]), enclose the value in quotes and brackets:\n"
                    "--item-inputs \"key=['value1','value2']\""
                )

        elif expected == "List[int]":
            if not isinstance(value, list) or not all(
                isinstance(i, int) for i in value
            ):
                type_errors.append(
                    f"'{key}' must be a list of integers."
                    " To pass a list (e.g. List[int]), enclose the value in quotes and brackets:\n"
                    "--item-inputs \"key=['value1','value2']\""
                )

        elif expected == "List[dict]":
            if not isinstance(value, list) or not all(
                isinstance(i, dict) for i in value
            ):
                type_errors.append(
                    f"'{key}' must be a list of dictionaries."
                    " To pass a list (e.g. List[int]), enclose the value in quotes and brackets:\n"
                    "--item-inputs \"key=['value1','value2']\""
                )
        else:
            type_errors.append(f"Unknown expected type for '{key}': {expected}")

    if type_errors:
        return "Invalid input types:\n  " + "\n  ".join(type_errors)

    return ""


@ewc_hub_command.command("deploy")
@common_context
@ssh_options
@ssh_options_encoded
@openstack_options
@openstack_optional_options
@click.option(
    "--server-name",
    is_flag=False,
    required=False,
    default=None,
    envvar="EWC_CLI_INSTANCE_NAME",
    show_default=False,
    help="Select a name for the server.",
)
@click.option(
    "--item-inputs",
    "-iu",
    envvar="EWC_CLI_ITEM_INPUTS",
    type=str,
    multiple=True,
    help=(
        "Input key=value pairs to configure item inputs. "
        "Supports comma-separated pairs in one argument or multiple uses of --item-inputs.\n\n"
        "Examples:\n"
        "--item-inputs key1=value1 --item-inputs key2=value2\n\n"
    ),
    callback=_validate_item_inputs_format,
)
@click.option(
    "--dry-run",
    envvar="EWC_CLI_DRY_RUN",
    default=False,
    is_flag=True,
    help="Simulate deployment without running.",
)
@click.option(
    "--config-name",
    envvar="EWC_CLI_LOGIN_CONFIG_NAME",
    required=False,
    callback=validate_config_name,
    help="EWC CLI config name, format: {tenant_name}-{region} (all alphanumeric)",
)
@click.option(
    "--force",
    envvar="EWC_CLI_FORCE",
    is_flag=True,
    default=False,
    help="Force item recreation operation.",
)
@click.argument(
    "item",
    type=str,
)
def deploy_cmd(  # noqa: CFQ002, CFQ001, CCR001, C901
    ctx,
    item: str,
    application_credential_id: str,
    application_credential_secret: str,
    dry_run: bool,
    force: bool,
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    keypair_name: str,
    server_name: Optional[str] = None,
    config_name: Optional[str] = None,
    item_inputs: Optional[dict] = None,
    auth_url: Optional[str] = None,
    image_name: Optional[str] = None,
    flavour_name: Optional[str] = None,
    external_ip: bool = False,
    networks: Optional[tuple] = None,
    security_groups: Optional[tuple] = None,
    ssh_private_encoded: Optional[str] = None,
    ssh_public_encoded: Optional[str] = None,
):
    """Deploy EWC Hub item.

    ewc hub deploy <item>

    where <item> is taken from ewc hub list command (under Item column)
    """
    if dry_run:
        _LOGGER.info("Dry run enabled...")

    if config_name:
        retrieve_region, tenant_name = split_config_name(config_name=config_name)
        cli_config = load_cli_config(tenant_name=tenant_name, region=retrieve_region)
    else:
        cli_config = load_cli_config()

    region: str = cli_config["region"]
    federee = region
    # Take item information
    _LOGGER.info(f"The item will be deployed on {federee} side of the EWC.")

    #################################################################################
    # Retrieve item and item info
    #################################################################################
    item = os.getenv("EWC_CLI_HUB_ITEM") or item
    console.print(f"You selected {item} item from the EWC Community Hub.")

    item_info, required_item_inputs, default_item_inputs = _extract_item_inputs_class(
        ctx, item
    )

    if item_inputs is None:
        item_inputs = {}

    # Validate inputs
    item_info_ewccli = item_info.get(HubItemCLIKeys.ROOT.value, {})
    all_item_inputs = item_info_ewccli.get(HubItemCLIKeys.INPUTS.value, [])
    validation_message = _validate_item_input_types(
        parsed_inputs=item_inputs,
        schema=all_item_inputs,
    )

    if validation_message:
        raise click.UsageError(validation_message)

    # Check for missing mandatory parameters
    missing_keys = _validate_required_inputs(
        parsed_inputs=item_inputs, required_item_inputs=required_item_inputs
    )

    if missing_keys:
        message = prepare_missing_inputs_error_message(missing_keys)
        raise click.UsageError(
            f"{message}\n"
            "Provide key=value pairs for item inputs. "
            "Use this option multiple times for multiple inputs.\n\n"
            "For example:\n"
            "--item-inputs key1=value1 --item-inputs key2=value2\n\n"
            "To pass a list (e.g. List[str]), enclose the value in quotes and brackets:\n"
            "--item-inputs \"key=['value1','value2']\""
        )

    #####################################################################################
    # Prepare item parameters
    #####################################################################################
    sources = item_info.get("sources")
    if not sources:
        raise ClickException(f"{item} item doesn't contain any sources.")

    source = sources[0]
    version = item_info.get("version")
    annotations = item_info.get("annotations")

    annotations_category, annotations_technology = extract_annotations(
        annotations=annotations
    )

    # Give name to the server
    # TODO: add -state to terraform items, add -charts to helm chart items
    if not server_name:
        server_name = item

    # Define path for ~/.ewccli where everything is stored
    # random_id = generate_random_id()
    # cwd_command = f"{ewc_hub_config.EWC_CLI_DEFAULT_PATH_OUTPUTS}/{item}-{random_id}"
    command_path = f"{ewc_hub_config.EWC_CLI_DEFAULT_PATH_OUTPUTS}/{item}-{version}"
    repo_name = os.path.splitext(source.split("/")[-1])[0]

    ########################################################################
    # Git clone item to be deployed
    ########################################################################
    git_clone_return_code, git_clone_message = git_clone_item(
        source=source,
        repo_name=repo_name,
        command_path=command_path,
        dry_run=dry_run,
        force=force,
    )

    if git_clone_return_code == 0:
        _LOGGER.debug("✅ Command executed successfully.")

        if git_clone_message:
            _LOGGER.info(git_clone_message)

    else:
        error_message = (
            f"❌ Command failed with return code {git_clone_return_code}.\n"
            f"📥 STDERR:\n{git_clone_message if git_clone_message else 'No error output provided.'}\n\n"
            "💡 Hint: Ensure the repository URL is correct and accessible, "
            "and that your network and credentials are properly configured."
        )
        raise ClickException(error_message)

    ########################################################################
    # Run logic based on the technology annotation of the item
    ########################################################################

    is_gpu = (
        True
        if HubItemCategoryAnnotation.GPU_ACCELERATED.value in annotations_category
        else False
    )

    if (
        HubItemTechnologyAnnotation.ANSIBLE.value in annotations_technology
        and len(annotations_technology) == 1
    ):
        _LOGGER.info(
            f"The item {item} uses {HubItemTechnologyAnnotation.ANSIBLE.value} techonology."
        )

        application_credential_id = (
            cli_config.get("application_credential_id") or application_credential_id
        )
        application_credential_secret = (
            cli_config.get("application_credential_secret")
            or application_credential_secret
        )
        if not auth_url:
            auth_url = ewc_hub_config.EWC_CLI_SITE_MAP.get(federee)

        try:
            openstack_backend = OpenstackBackend(
                application_credential_id=application_credential_id,
                application_credential_secret=application_credential_secret,
                auth_url=auth_url,
            )
        except Exception as op_error:
            raise ClickException(
                f"Could not initialize Openstack config due to the following error: {op_error}"
            )

        #####################################################################################
        # Authenticate to Openstack
        #####################################################################################

        try:
            # Step 1: Authenticate and initialize the OpenStack connection
            openstack_api = openstack_backend.connect(
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
            "is_gpu": is_gpu,
            "image_name": item_info_ewccli.get(HubItemCLIKeys.DEFAULT_IMAGE_NAME.value) or image_name,
            "keypair_name": keypair_name,
            "flavour_name": flavour_name,
            "external_ip": external_ip,
            "networks": networks,
            "security_groups": security_groups,
        }

        os_status_code, os_message, outputs = deploy_server(
            openstack_backend=openstack_backend,
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

        # Assign correct default values to default item_inputs
        for d_item in default_item_inputs:
            default_item_input_name = d_item.get("name")

            if default_item_input_name not in item_inputs:
                if default_item_input_name in HUB_ENV_VARIABLES_MAP:
                    item_inputs[default_item_input_name] = (
                        get_hub_item_env_variable_value(
                            hub_item_env_variables_map=HUB_ENV_VARIABLES_MAP,
                            federee=region,
                            variable_name=default_item_input_name,
                            openstack_api=openstack_api,
                        )
                    )
                else:
                    item_inputs[default_item_input_name] = d_item.get("default")

        # Install requirements for ansible playbook
        requirements_file_relative_path = item_info_ewccli.get(HubItemCLIKeys.ITEM_PATH_TO_REQUIREMENTS_FILE.value, "requirements.yml")

        # Run main ansible playbook
        main_file_relative_path = item_info_ewccli.get(HubItemCLIKeys.ITEM_PATH_TO_MAIN_FILE.value)

        if not main_file_relative_path:
            raise ClickException(f"{HubItemCLIKeys.ITEM_PATH_TO_MAIN_FILE.value} key for {item} is not set. The Ansible playbook item cannot be installed.")

        main_file_path = f"{command_path}/{repo_name}/{main_file_relative_path}"

        ansible_status_code, ansible_message = run_ansible_playbook_item(
            item=item,
            item_inputs=item_inputs,
            server_name=server_name,
            username=username,
            repo_name=repo_name,
            main_file_path=main_file_path,
            requirements_file_relative_path=requirements_file_relative_path,
            command_path=command_path,
            ip_machine=(
                external_ip_machine if external_ip_machine else internal_ip_machine
            ),
            ssh_private_key_path=str(ssh_private_key_path),
            dry_run=dry_run,
        )

        if os_status_code != 0:
            raise ClickException(os_message)
        elif ansible_status_code != 0:
            raise ClickException(ansible_message)
        else:
            show_item_table(hub_item=item_info)

            # Build the message
            message = "[bold blue]🚀 Deployment Complete[/bold blue]\n"
            message += f"[bold]Item:[/bold] {item}-{version} has been successfully deployed.\n\n"

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

            current_user = default_username()
            message += (
                f"[bold green]ssh -i [underline]{ssh_private_key_path}[/underline]"
                f" {username}@{external_ip_machine if external_ip_machine else internal_ip_machine}[/bold green]\n\n"
                "Alternatively, if your machine is enrolled to the same IPA domain of your current machine,"
                " and you are in the same network, you can use the hostname directly:\n\n"
                f"[bold green]ssh {current_user}@{server_name}[/bold green]"
            )
            console.print(message)

    elif (
        HubItemTechnologyAnnotation.TERRAFORM.value in annotations_technology
        and len(annotations_technology) == 1
    ):
        _LOGGER.info(
            f"The item {item} uses {HubItemTechnologyAnnotation.TERRAFORM.value} techonology."
        )
        _LOGGER.warning(
            f"EWC CLI cannot handle {HubItemTechnologyAnnotation.TERRAFORM.value} technology yet. Exiting."
        )

        # Check if terraform is installed and ask to install it if not.
    else:
        _LOGGER.info(
            f"The item {item} uses {' & '.join(annotations_technology)} techonology. "
            "EWC CLI cannot handle this case yet. Exiting"
        )


@ewc_hub_command.command("list")
@hub_context
def list_cmd(ctx):
    """List EWC Hub items."""
    list_items_table(hub_items=ctx.items)


@ewc_hub_command.command("show")
@hub_context
@click.argument(
    "item",
    type=str,
)
def show_cmd(ctx, item):
    """Show information on a specific EWC Hub item.

    ewc hub show <item>

    where <item> is taken from ewc hub list command.
    """
    if item not in [i for i, _ in ctx.items.items()]:
        list_items_table(
            hub_items=ctx.items,
        )
        raise ClickException(
            f"{item} is not available in the EWC Hub. Please check the list above."
        )

    else:
        show_item_table(
            hub_item=ctx.items.get(item),
            default_admin_variables_map=HUB_ENV_VARIABLES_MAP,
        )
