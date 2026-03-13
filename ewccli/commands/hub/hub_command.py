#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Hub: EWC Hub interaction."""

import os
import sys
import yaml
import typing
from pathlib import Path
from typing import Optional, List, Dict, Any

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from click import ClickException
from click import get_current_context
from pydantic import ValidationError, create_model

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import download_items
from ewccli.commands.hub.hub_utils import verify_item_is_deployable
from ewccli.commands.hub.hub_utils import extract_annotations
from ewccli.commands.hub.hub_utils import prepare_missing_inputs_error_message
from ewccli.commands.hub.hub_utils import classify_source
from ewccli.commands.commons import openstack_options
from ewccli.commands.commons import ssh_options
from ewccli.commands.commons import ssh_options_encoded
from ewccli.commands.commons import openstack_optional_options
from ewccli.commands.commons import list_items_table
from ewccli.commands.commons import show_item_table
from ewccli.commands.commons import default_username
from ewccli.commands.commons import build_dns_record_name
from ewccli.commands.commons import wait_for_dns_record
from ewccli.commands.commons import load_hub_items
from ewccli.commands.commons_infra import deploy_server
from ewccli.commands.commons_infra import check_user_ssh_keys
from ewccli.commands.hub.hub_backends import git_clone_item
from ewccli.commands.hub.hub_backends import run_ansible_playbook_item
from ewccli.commands.hub.hub_backends import get_hub_item_env_variable_value
from ewccli.commands.hub.hub_backends import HUB_ENV_VARIABLES_MAP
from ewccli.backends.openstack.backend_ostack import OpenstackBackend
from ewccli.enums import HubItemTechnologyAnnotation
from ewccli.enums import HubItemCategoryAnnotation
from ewccli.enums import HubItemCLIKeys
from ewccli.logger import get_logger
from ewccli.utils import load_cli_profile

_LOGGER = get_logger(__name__)

console = Console()


@click.group(name="hub")
@click.option(
    "--path-to-catalog",
    is_flag=False,
    required=False,
    type=click.Path(path_type=Path),
    default=ewc_hub_config.EWC_CLI_HUB_ITEMS_PATH,
    envvar="EWC_CLI_PATH_TO_CATALOGUE",
    show_default=True,
    help="EWC CLI path to catalogue.",
)
@click.pass_context
def ewc_hub_command(ctx, path_to_catalog):
    """EWC Community Hub commands group."""
    download_items(force=ewc_hub_config.EWC_CLI_HUB_DOWNLOAD_ITEMS)

    # Create the dict if not existing
    ctx.ensure_object(dict)

    if path_to_catalog:
        if not path_to_catalog.exists():
            raise click.ClickException(f"Catalog file doesn't exist at this path: {path_to_catalog}")

        # Check directory:
        if path_to_catalog.is_dir():
            raise click.ClickException(f"Catalog path must be a file not a directory: {path_to_catalog}")

        items = load_hub_items(path_to_catalog=path_to_catalog)

    else:
        items = load_hub_items()

    # Store the option to make it available to all subcommands
    ctx.obj['items'] = items

    ctx.obj['cli_profile'] = None


def categorize_item_inputs(
    ctx,
    item_info: dict,
    item_info_inputs: list
):  # noqa CCR001
    """Categorize item inputs into default and mandatory."""
    default_inputs = []
    required_inputs = []

    # if no inputs exist for the item, no inputs are requested from the user
    if not item_info_inputs:
        return required_inputs, default_inputs

    for item_input in item_info_inputs:
        # If there is a default, the item is part of the default inputs -> not required by the user
        if "default" in item_input:
            # default value exists
            default_inputs.append(item_input)

        # If the item input has no default, it should be mandatory, but if the variable is known by the ewccli,
        # because it's related to the infrastructure or it's very specific to EWC, then the default will be applied by the EWCCLI
        # TODO: Change once we have the new variable specific to ewccli default parameters (e.g. tenancy_name, network_name)
        elif item_input.get("name", "") in HUB_ENV_VARIABLES_MAP:
            default_inputs.append(item_input)
        else:
            # In other case, the input is mandatory and it needs to be provided by the user.
            required_inputs.append(item_input)

    ctx = get_current_context()  # <-- Get Click Context

    ctx.command.params[3].type = click.Choice(required_inputs)
    ctx.command.params[3].required = True
    ctx.command.params[3].nargs = len(required_inputs)

    return required_inputs, default_inputs


def check_missing_required_inputs(
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


def validate_item_input_types(
    parsed_inputs: Optional[dict], item_info_inputs: Optional[list]
) -> str:
    """
    Validate parsed_inputs against a schema using Pydantic.

    schema example:
    [
        {"name": "foo", "type": "str"},
        {"name": "bar", "type": "List[int]"},
        {"name": "baz", "type": "Optional[str]"},
        {"name": "qux", "type": "Union[str, int]"},
    ]

    Returns:
        "" if all inputs are valid, otherwise a string describing invalid inputs.
    """
    if not item_info_inputs or not parsed_inputs:
        return ""

    # # Prepare safe globals with all typing names
    safe_globals = {k: getattr(typing, k) for k in dir(typing) if not k.startswith("_")}
    safe_globals.update({"Any": Any})  # Add Any from builtins

    # Build a dict of pydantic fields: { field_name: (python_type, required) }
    fields = {}
    expected_types_map = {}  # Keep original type strings for error messages

    for entry in item_info_inputs:
        name = entry["name"]
        type_expr = entry["type"]
        expected_types_map[name] = type_expr  # Save for later display

        try:
            py_type = eval(type_expr, safe_globals)
        except Exception:
            py_type = Any

        fields[name] = (py_type, ...)  # ... = required field

    # Create a dynamic Pydantic model
    DynamicInputs = create_model("DynamicInputs", **fields)

    try:
        DynamicInputs(**parsed_inputs)
        return ""

    except ValidationError as e:
        # Build detailed error messages including expected type
        error_lines = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            msg = err["msg"]
            expected_type = expected_types_map.get(err["loc"][0], "Unknown")
            error_lines.append(f"{loc}: {msg} (expected type: {expected_type})")

        return "Invalid input types:\n  " + "\n  ".join(error_lines)


class KeyValueType(click.ParamType):
    """Class for key=value pairs."""

    name = "key=value"

    def convert(self, value, param, ctx):
        """Conver key value pairs inputs to Python literals."""
        if "=" not in value:
            self.fail(f"'{value}' is not in key=value format", param, ctx)

        key, raw_value = value.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        _LOGGER.debug(f"Input name: {key}")
        _LOGGER.debug("Raw value datatype (taken from CLI)")
        _LOGGER.debug(type(raw_value))
        try:
            # Parse value using YAML syntax
            parsed_value = yaml.safe_load(raw_value)
        except Exception:
            parsed_value = raw_value  # fallback to string
        _LOGGER.debug("Parsed value datatype (using yaml.safe_load in Python)")
        _LOGGER.debug(type(parsed_value))
        return key, parsed_value


_ITEM_INPUT_MESSAGE = (
    "Provide item input as key=value. "
    "May be passed multiple times.\n\n"
    "Examples:\n"
    "  --item-inputs key1=value1\n"
    "  --item-inputs retries=3\n"
    "  --item-inputs names=\"['a', 'b']\"\n\n"
    "Note:\n"
    "  When passing lists or dictionaries, the syntax used to parse inputs is same as yaml.\n"
)

def _validate_item_inputs_format(ctx, param, values):
    if not values:
        return {}

    parsed = {}

    for key, val in values:
        parsed[key] = val

    return parsed


def _validate_item(ctx, param, value):
    """Validate that the provided item exists in the Hub and is deployable."""
    hub_items = ctx.obj.get("items", {})

    # Check If item does not exist at all
    if value not in hub_items:
        list_items_table(hub_items=hub_items)
        raise ClickException(
            f"'{value}' is not available in the EWC Hub. Please select an item from the list above."
        )

    item_info = hub_items[value]

    # If item exists check if it is *not deployable*
    is_item_deployable = verify_item_is_deployable(item_info)
    if not is_item_deployable:
        raise ClickException(f"❌ Item {value} is not deployable. Exiting.")

    return value


@ewc_hub_command.command("deploy")
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
    type=KeyValueType(),
    multiple=True,
    help=f"{_ITEM_INPUT_MESSAGE}",
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
    "--profile",
    envvar="EWC_CLI_LOGIN_PROFILE",
    required=False,
    default=ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME,
    help="EWC CLI profile name",
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
    callback=_validate_item,
)
@click.pass_context
def deploy_cmd(  # noqa: CFQ002, CFQ001, CCR001, C901
    ctx,
    item: str,
    application_credential_id: str,
    application_credential_secret: str,
    dry_run: bool,
    force: bool,
    keypair_name: str,
    ssh_public_key_path: Optional[str] = None,
    ssh_private_key_path: Optional[str] = None,
    server_name: Optional[str] = None,
    profile: Optional[str] = None,
    item_inputs: Optional[Any] = None,
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

    if profile:
        cli_profile = load_cli_profile(profile=profile)
    else:
        # Use default profile if exists
        cli_profile = load_cli_profile(
            profile=ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME
        )

    _LOGGER.info(f"Using `{cli_profile.get('profile')}` profile.")

    tenancy_name = cli_profile["tenant_name"]
    federee: str = cli_profile["federee"]

    # Try to fill from CLI profile if not provided
    if not ssh_public_key_path:
        ssh_public_key_path = ctx.cli_profile.get("ssh_public_key_path")

    if not ssh_private_key_path:
        ssh_private_key_path = ctx.cli_profile.get("ssh_private_key_path")

    check_user_ssh_keys(
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path
    )

    # Take item information
    _LOGGER.info(f"The item will be deployed on {federee} side of the EWC.")

    #################################################################################
    # Retrieve item and item info
    #################################################################################
    item = os.getenv("EWC_CLI_HUB_ITEM") or item
    console.print(f"You selected {item} item from the EWC Community Hub.")

    item_info = ctx.obj['items'][item]

    # Retrieve item inputs of the selected item from the catalogue
    item_info_ewccli = item_info.get(HubItemCLIKeys.ROOT.value, {})
    item_info_inputs = item_info_ewccli.get(HubItemCLIKeys.INPUTS.value, [])

    # Categorize items inputs from the item info in the catalog (Required and Default)
    required_item_inputs, default_item_inputs = categorize_item_inputs(
        ctx, item_info=item_info, item_info_inputs=item_info_inputs
    )

    # If no item inputs provided by the user, make default as empty dictionary
    if item_inputs is None:
        item_inputs = {}

    ###################################
    # Check missing required parameters
    ###################################

    missing_keys = check_missing_required_inputs(
        parsed_inputs=item_inputs, required_item_inputs=required_item_inputs
    )

    if missing_keys:
        message = prepare_missing_inputs_error_message(missing_keys)
        raise click.UsageError(
            f"{message}\n\n"
            f"{_ITEM_INPUT_MESSAGE}"
        )

    #####################################################################################
    # Prepare item parameters
    #####################################################################################
    sources = item_info.get("sources")
    if not sources:
        raise ClickException(f"{item} item doesn't contain any sources.")

    # Consider annotations
    annotations = item_info.get("annotations")
    annotations_category, annotations_technology = extract_annotations(
        annotations=annotations
    )

    # Give name to the server
    # TODO: add -state to terraform items, add -charts to helm chart items
    if not server_name:
        server_name = item

    # Consider first element in the list!
    source = sources[0]
    version = item_info.get("version")

    is_source = classify_source(source=source)

    _LOGGER.info(f"📦 Classified source '{source}' as: [blue]{is_source}[/blue]")

    working_directory_path = None

    if is_source == "directory":
        #################################################################################
        # Use local item (code is still local not available in any public git repository)
        #################################################################################
        working_directory_path = source

    if is_source == "github":
        #############################################################################
        # Git clone item to be deployed (public repository available in the internet)
        #############################################################################
        # Define path for ~/.ewccli where everything is stored
        # random_id = generate_random_id()
        # cwd_command = f"{ewc_hub_config.EWC_CLI_DEFAULT_PATH_OUTPUTS}/{item}-{random_id}"
        command_path = f"{ewc_hub_config.EWC_CLI_DEFAULT_PATH_OUTPUTS}/{item}-{version}"
        repo_name = os.path.splitext(source.split("/")[-1])[0]
        working_directory_path = f"{command_path}/{repo_name}"

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

    if not working_directory_path:
        raise ClickException(f"Working directory path is empty, please verify sources metadata in your hub catalogue for {item} item")

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
            cli_profile.get("application_credential_id") or application_credential_id
        )
        application_credential_secret = (
            cli_profile.get("application_credential_secret")
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

        ##########################################
        # Validate inputs
        ###########################################
        # R = required
        # D = default
        # catalog -> D (yaml inputs)
        # user -> R or D (overwrite) (bash inputs)
        ###########################################

        # Prepare default parameters
        for d_item in default_item_inputs:
            default_item_input_name = d_item.get("name")

            # If default value is not provided by the user.
            if default_item_input_name not in item_inputs:
                # TODO: Improve this logic with new parameter in the catalog
                # Take the default from the EWC values if they exist
                if default_item_input_name in HUB_ENV_VARIABLES_MAP:
                    item_inputs[default_item_input_name] = (
                        get_hub_item_env_variable_value(
                            hub_item_env_variables_map=HUB_ENV_VARIABLES_MAP,
                            federee=federee,
                            tenancy_name=tenancy_name,
                            variable_name=default_item_input_name,
                            openstack_api=openstack_api,
                        )
                    )
                else:
                    # Take the default from the catalog
                    item_inputs[default_item_input_name] = d_item.get("default")

        # Validate all input parameters (R + D)
        # (R) Validate required inputs
        # (D) Validate default inputs provided by user (overwritten) or from default section of the catalog
        validation_message = validate_item_input_types(
            parsed_inputs=item_inputs,
            item_info_inputs=item_info_inputs,
        )

        if validation_message:
            raise click.UsageError(validation_message)

        #####################################################################################
        # Deploy Server
        #####################################################################################

        security_groups_inputs = ()

        if security_groups:
            security_groups_inputs += security_groups

        item_default_security_groups = item_info_ewccli.get(
            HubItemCLIKeys.DEFAULT_SECURITY_GROUPS.value
        )
        if item_default_security_groups:
            security_groups_inputs += tuple(dsc for dsc in item_default_security_groups)

        server_inputs = {
            "server_name": server_name,
            "is_gpu": is_gpu,
            "image_name": item_info_ewccli.get(HubItemCLIKeys.DEFAULT_IMAGE_NAME.value) if not image_name else image_name,
            "keypair_name": keypair_name,
            "flavour_name": flavour_name,
            "external_ip": external_ip
            or item_info_ewccli.get(HubItemCLIKeys.EXTERNAL_IP.value),
            "networks": networks,
            "security_groups": security_groups_inputs,
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
            console.print(Panel(os_message, title="Error", style="red"))
            # Exit with a non-zero status
            sys.exit(1)

        internal_ip_machine = outputs["internal_ip_machine"]
        external_ip_machine = outputs.get("external_ip_machine")
        normalized_image_name = outputs["normalized_image_name"]

        #### DNS CHECK

        check_dns = item_info_ewccli.get(HubItemCLIKeys.CHECK_DNS.value)

        if check_dns:
            if not external_ip_machine:
                raise ClickException(
                    f"This item {item} requires DNS check but you didn't add an external IP to the server,"
                    " please re run the command with --external-ip."
                )

            dns_record_name = build_dns_record_name(
                server_name=server_name,
                tenancy_name=tenancy_name,
                hosting_location=ewc_hub_config.FEDEREE_DNS_MAPPING[federee],
            )

            dns_record_check = wait_for_dns_record(
                dns_record_name=dns_record_name,
                expected_ip=external_ip_machine,
                timeout_minutes=ewc_hub_config.DNS_CHECK_TIMEOUT_MINUTES,
            )
            if not dns_record_check:
                raise ClickException(
                    f"EWC CLI failed to deploy {item} due to {dns_record_name} not found in DNS records of the hosted zone used in EWC."
                    f" This item {item} requires DNS record."
                    f" What can you do? You can try to run: dig {dns_record_name} in your terminal and once the public IP {external_ip_machine} is available,"
                    " you can rerun the item deployment with EWC CLI using the same command you just used. Alternatively, you can rerun the command"
                    " directly and the ewc cli will continue checking for the DNS record to be ready and continue from where it left."
                )

        #### ANSIBLE PLAYBOOK ITEM DEPLOYMENT
        username = (
            ewc_hub_config.EWC_CLI_IMAGES_USER.get(normalized_image_name)
        )

        # If missing the mapping in the configuration is missing, so configuration file needs to be checked.
        if not username:
            return (
                1,
                f"Username {username} is missing or empty",
                outputs,
            )

        # server_info = outputs.get("server_info")
        # external_network = outputs.get("external_network")

        # Install requirements for ansible playbook
        requirements_file_relative_path = item_info_ewccli.get(
            HubItemCLIKeys.ITEM_PATH_TO_REQUIREMENTS_FILE.value, "requirements.yml"
        )

        # Run main ansible playbook
        main_file_relative_path = item_info_ewccli.get(
            HubItemCLIKeys.ITEM_PATH_TO_MAIN_FILE.value
        )

        if not main_file_relative_path:
            raise ClickException(
                f"{HubItemCLIKeys.ITEM_PATH_TO_MAIN_FILE.value} key for {item} is not set. The Ansible playbook item cannot be installed."
            )

        main_file_path = f"{working_directory_path}/{main_file_relative_path}"
        requirements_file_path = (
            f"{working_directory_path}/{requirements_file_relative_path}"
        )

        ansible_status_code, ansible_message = run_ansible_playbook_item(
            item=item,
            item_inputs=item_inputs,
            server_name=server_name,
            username=username,
            main_file_path=main_file_path,
            requirements_file_path=requirements_file_path,
            working_directory_path=working_directory_path,
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
@click.option(
    "--force",
    envvar="EWC_CLI_FORCE",
    is_flag=True,
    default=False,
    help="Force item file re-download.",
)
@click.pass_context
def list_cmd(ctx, force: bool):
    """List EWC Hub items."""
    if force:
        download_items(force=force)

    list_items_table(hub_items=ctx.obj['items'])


@ewc_hub_command.command("show")
@click.argument(
    "item",
    type=str,
)
@click.pass_context
def show_cmd(ctx, item):
    """Show information on a specific EWC Hub item.

    ewc hub show <item>

    where <item> is taken from ewc hub list command.
    """
    if item not in [i for i, _ in ctx.obj['items'].items()]:
        list_items_table(
            hub_items=ctx.obj['items'],
        )
        raise ClickException(
            f"{item} is not available in the EWC Hub. Please check the list above."
        )

    else:
        show_item_table(
            hub_item=ctx.obj['items'].get(item),
            default_admin_variables_map=HUB_ENV_VARIABLES_MAP,
        )
