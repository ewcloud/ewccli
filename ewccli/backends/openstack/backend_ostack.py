#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Openstack backend methods."""

import time
import sys
import os
from typing import Tuple, Optional, Any
from collections import namedtuple
from pathlib import Path

import openstack
from openstack.config import OpenStackConfig
from openstack.exceptions import ConfigException
from openstack.compute.v2.server import Server

from ewccli.logger import get_logger
from ewccli.enums import Federee
from ewccli.configuration import config as ewc_hub_config

_LOGGER = get_logger(__name__)

# Results.
# success   is True on success.
# changed   If successful, changed is True if the server was created,
#           and False if it already existed.
# failures  The number of server creation failures creating the server
ServerResult = namedtuple("ServerResult", "success changed failures")
KeyPairResult = namedtuple("KeyPairResult", "success changed")
ExternalIPResult = namedtuple("ExternalIPResult", "success changed")
NetworkResult = namedtuple("NetworkResult", "success changed")
_MAX_CHARACTERS_SERVER_NAME_OPENSTACK = 63


class OpenstackBackend:
    """Openstack backend class."""

    def __init__(
        self,
        application_credential_id: Optional[str] = None,
        application_credential_secret: Optional[str] = None,
        auth_url: Optional[str] = None,
    ):
        """
        Initialize the OpenStack backend.

        :param application_credential_id: OpenStack application credential ID.
        :param application_credential_secret: OpenStack application credential secret.
        :param auth_url: Openstack Auth URL
        """
        try:
            if application_credential_id and application_credential_secret:
                # Try loading from parameters or fall back to env vars
                self.credential_id = application_credential_id or os.getenv(
                    "OS_APPLICATION_CREDENTIAL_ID"
                )
                self.credential_secret = application_credential_secret or os.getenv(
                    "OS_APPLICATION_CREDENTIAL_SECRET"
                )
                self.auth_url = auth_url
            else:
                config = (
                    OpenStackConfig()
                )  # ~/.config/openstack/clouds.yaml, to change use OS_CLIENT_CONFIG_FILE
                # Get the default cloud if no name is specified
                cloud = (
                    config.get_one()
                )  # It can be set with OS_CLOUD directly in Openstack
                cloud_config = cloud.config.get("auth")
                self.credential_id = cloud_config.get("application_credential_id")
                self.credential_secret = cloud_config.get(
                    "application_credential_secret"
                )
                self.auth_url = cloud_config.get("auth_url")

        except (ConfigException, Exception) as e:
            _LOGGER.error(
                f"🔐 Missing OpenStack credentials.: {e}\n\n"
                "❌ No config found. Run `ewc login` first or have a cloud.yaml"
                " under ~/.config/openstack/clouds.yaml or set the following environment variables:\n"
                "-OS_APPLICATION_CREDENTIAL_ID"
                "-OS_APPLICATION_CREDENTIAL_SECRET"
            )

    def connect(
        self,
        auth_url: Optional[str] = None,
        application_credential_id: Optional[str] = None,
        application_credential_secret: Optional[str] = None,
        app_version: str = "3",
        auth_type: str = "v3applicationcredential",
    ):
        """Create connection to Openstack.

        :param auth_url: Openstack authorization URL
        :param application_credential_id=application_credential_id
        :param application_credential_secret=application_credential_secret
        :param user_domain_name == domain_name
        :param project_domain_name == domain_id

        """
        os_app_credential_id = application_credential_id or self.credential_id
        os_app_credential_secret = (
            application_credential_secret or self.credential_secret
        )
        os_auth_url = auth_url or self.auth_url

        os_connection = openstack.connect(
            auth_url=os_auth_url,
            auth_type=auth_type,
            # tenant_name=tenant_name,
            application_credential_id=os_app_credential_id,
            application_credential_secret=os_app_credential_secret,
            # username=username,
            # password=password,
            # region_name=region,
            # user_domain_name=user_domain_name,
            # project_domain_name=project_domain_name,
            app_version=app_version,
        )

        return os_connection

    def create_server(
        self,
        conn: openstack.connection.Connection,
        server_name: str,
        image_name: str,
        flavour_name: str,
        networks: tuple,
        keypair_name: str,
        sec_groups: tuple,
        attempts: int = 1,
        retry_delay_s: int = 30,
        wait_time_s: int = 600,
        dry_run: bool = False,
    ) -> Tuple[ServerResult, Optional[str], dict[Any, Any]]:
        """Create an OpenStack server.

        Automatically deletes and retries the creation process until a server is available.
        Once the creation attempts have been exhausted the function returns False.

        The server creation can fail, that's fatal for us. If the
        'wait' fails then we created a server and it failed for some reason.
        We delete the server and try again under these circumstances.

        :param conn: The OpenStack connection
        :param server_name: The server name
        :param image_name: The server instance base image
        :param flavour_name: The server flavour (type), i.e. 'c2.large'
        :param networks: list of networks for the VM (tuple)
        :param keypair_name: The OpenStack SSH key-pair to use (this must exist)
        :param sec_groups: list of security groups for the VM (tuple)
        :param attempts: The number of create attempts. If the server fails
                        this function uses this value to decide whether to try
                        ans create it.
        :param retry_delay_s: The delay between creation attempts.
        :param wait_time_s: The maximum period to wait (for creation or deletion).
        :param dry_run: Dry run.
        """
        if len(server_name) > _MAX_CHARACTERS_SERVER_NAME_OPENSTACK:
            _LOGGER.error(
                f"server_name cannot exceed {_MAX_CHARACTERS_SERVER_NAME_OPENSTACK},"
                " please select a shorter name"
            )
            sys.exit(1)

        # Do nothing if the server appears to exist
        server_info = conn.get_server(name_or_id=server_name)

        if server_info:
            # Yes!
            # Success, unchanged
            return (
                ServerResult(True, False, 0),
                f"{server_name} VM already exists on Openstack. No VM will be created.",
                server_info,
            )

        if dry_run and not server_info:
            return (
                ServerResult(True, False, 0),
                "Dry run on. No actions will be performed",
                {},
            )

        _LOGGER.info("⏳ This could take a few minutes, grab a coffee ☕️ meanwhile...")
        openstack_image_name = image_name
        image = conn.compute.find_image(openstack_image_name)

        if not image:
            return ServerResult(False, False, 0), f"Unknown image ({image_name})", {}

        flavour = conn.compute.find_flavor(flavour_name)

        if not flavour:
            for flavor in conn.compute.flavors():
                _LOGGER.info(
                    f"Name: {flavor.name}, ID: {flavor.id}, VCPUs: {flavor.vcpus}, RAM: {flavor.ram} MB"
                )

            return (
                ServerResult(False, False, 0),
                f"Unknown flavour ({flavour_name}). Check list above.",
                {},
            )

        security_group_names = []

        for security_group_name in sec_groups:
            sec_group_name = conn.get_security_group(security_group_name)

            if not sec_group_name:
                for sg in conn.network.security_groups():
                    _LOGGER.info(
                        f"Name: {sg.name}, ID: {sg.id}, Description: {sg.description or 'No description'}"
                    )
                return (
                    ServerResult(False, False, 0),
                    f"Unknown security group ({security_group_name}). Check list above.",
                    {},
                )

            security_group_names.append({"name": sec_group_name.name})

        network_info = []

        if networks:
            for network_name in networks:
                network = conn.network.find_network(network_name)

                if not network:
                    _LOGGER.error(f"Unknown network ({network_name})")

                    for network in conn.network.networks():
                        _LOGGER.info(f"Name: {network.name}, ID: {network.id}")

                    return (
                        ServerResult(False, False, 0),
                        f"Unknown network ({network_name})",
                        {},
                    )

                network_info.append({"uuid": network.id})

        # The number of times we had to re-create this server instance.
        num_create_failures = 0

        attempt = 1
        success = False
        new_server: Server = {}
        error_message = ""

        while not success and attempt <= attempts:
            _LOGGER.info(f"Creating {server_name} (attempt n.{attempt}/{attempts})...")

            try:
                # name – Something to name the server.
                # image – Image dict, name or ID to boot with. image is required unless boot_volume is given.
                # flavor – Flavor dict, name or ID to boot onto.
                # auto_ip – Whether to take actions to find a routable IP for the server. (defaults to True)
                # ips – List of IPs to attach to the server (defaults to None)
                # ip_pool – Name of the network or floating IP pool to get an address from. (defaults to None)
                # root_volume – Name or ID of a volume to boot from (defaults to None - deprecated,
                #   use boot_volume)
                # boot_volume – Name or ID of a volume to boot from (defaults to None)
                # terminate_volume – If booting from a volume, whether it should be deleted
                #    when the server is destroyed. (defaults to False)
                # volumes – (optional) A list of volumes to attach to the server
                # metadata – (optional) A dict of arbitrary key/value metadata to store for this server.
                #   Both keys and values must be <=255 characters.
                # files – (optional, deprecated) A dict of files to overwrite on the server upon boot.
                #   Keys are file names (i.e. /etc/passwd) and values are the file contents
                #   (either as a string or as a file-like object). A maximum of five entries is allowed,
                #   and each file must be 10k or less.
                # reservation_id – a UUID for the set of servers being requested.
                # min_count – (optional extension) The minimum number of servers to launch.
                # max_count – (optional extension) The maximum number of servers to launch.
                # security_groups – A list of security group names
                # userdata – user data to pass to be exposed by the metadata server
                #   this can be a file type object as well or a string.
                # key_name – (optional extension) name of previously created keypair
                #   to inject into the instance.
                # availability_zone – Name of the availability zone for instance placement.
                # block_device_mapping – (optional) A dict of block device mappings for this server.
                # block_device_mapping_v2 – (optional) A dict of block device mappings for this server.
                # nics – (optional extension) an ordered list of nics to be added to this server,
                #   with information about connected networks, fixed IPs, port etc.
                # scheduler_hints – (optional extension) arbitrary key-value pairs
                #   specified by the client to help boot an instance
                # config_drive – (optional extension) value for config drive either boolean, or volume-id
                # disk_config – (optional extension) control how the disk is partitioned
                #   when the server is created. possible values are ‘AUTO’ or ‘MANUAL’.
                # admin_pass – (optional extension) add a user supplied admin password.
                # wait – (optional) Wait for the address to appear as assigned to the server.
                #   Defaults to False.
                # timeout – (optional) Seconds to wait, defaults to 60. See the wait parameter.
                # reuse_ips – (optional) Whether to attempt to reuse pre-existing floating ips
                #   should a floating IP be needed (defaults to True)
                # network – (optional) Network dict or name or ID to attach the server to.
                #   Mutually exclusive with the nics parameter. Can also be a list of network names
                #   or IDs or network dicts.
                # boot_from_volume – Whether to boot from volume. ‘boot_volume’ implies True,
                #   but boot_from_volume=True with no boot_volume is valid and will create a volume
                #   from the image and use that.
                # volume_size – When booting an image from volume, how big should the created volume be?
                #    Defaults to 50.
                # nat_destination – Which network should a created floating IP be attached to,
                #   if it’s not possible to infer from the cloud’s configuration. (Optional, defaults to None)
                # group – ServerGroup dict, name or id to boot the server in.
                #   If a group is provided in both scheduler_hints and in the group param,
                #   the group param will win.
                #   (Optional, defaults to None)
                server = conn.compute.create_server(
                    name=server_name,
                    image_id=image.id,
                    flavor_id=flavour.id,
                    security_groups=security_group_names,
                    key_name=keypair_name,
                    networks=network_info,
                    metadata={"deployed": "ewccli"},
                )

                time.sleep(5)

            except openstack.exceptions.HttpException as ex:
                # Something wrong creating the server.
                # Nothing we can do here.
                return (
                    ServerResult(False, False, 0),
                    f"HttpException ({server_name}): {ex}",
                    {},
                )

            try:
                _LOGGER.info(f"Waiting for {server_name}...")
                new_server = conn.compute.wait_for_server(server, wait=wait_time_s)

            except openstack.exceptions.ResourceFailure:
                error_message = f"ResourceFailure ({server_name})"
            except openstack.exceptions.ResourceTimeout:
                error_message = f"ResourceTimeout/create ({server_name})"

            if new_server:
                success = True
            else:
                # Failed to create a server.
                # Count it.
                num_create_failures += 1

                _LOGGER.error(f"Failed ({server_name}) attempt no {attempt}.")

                # Delete the instance
                # (unless this is our last attempt)
                if attempt < attempts:
                    _LOGGER.info(f"Deleting... ({server_name})")
                    # Delete the instance
                    # and wait for it...
                    conn.compute.delete_server(server)

                    try:
                        conn.compute.wait_for_delete(server, wait=wait_time_s)
                    except openstack.exceptions.ResourceTimeout:
                        error_message = f"ResourceTimeout/delete ({server_name})"

                    _LOGGER.info(f"Pausing {retry_delay_s} seconds before retrying...")
                    time.sleep(retry_delay_s)
                attempt += 1

        # Set 'changed'.
        # If not successful this is ignored.
        if success:
            return (
                ServerResult(success, True, num_create_failures),
                f"Successfully created server {server_name}.",
                new_server,
            )
        else:
            return (
                ServerResult(success, True, num_create_failures),
                error_message,
                new_server,
            )

    def check_server_inputs(
        self,
        conn: openstack.connection.Connection,
        image_name: Optional[str] = None,
        flavour_name: Optional[str] = None,
        networks: Optional[tuple] = None,
        security_groups: Optional[tuple] = None,
    ) -> Tuple[bool, str]:
        """Check inputs before creating the server."""
        if image_name:
            image = conn.compute.find_image(image_name)

            if not image:
                valid_images = ", ".join(ewc_hub_config.EWC_CLI_IMAGES.values())
                message = (
                    f"❌ Unknown image '{image_name}'. "
                    f"Available options are: {valid_images}"
                )
                return False, message

        if flavour_name:
            flavour = conn.compute.find_flavor(flavour_name)

            if not flavour:
                for flavor in conn.compute.flavors():
                    _LOGGER.info(
                        f"Name: {flavor.name}, ID: {flavor.id}, VCPUs: {flavor.vcpus}, RAM: {flavor.ram} MB"
                    )

                return False, f"Unknown flavour ({flavour_name}). Check list above."

        if security_groups is not None:
            for security_group_name in security_groups:
                sec_group_name = conn.get_security_group(security_group_name)

                if not sec_group_name:
                    for sg in conn.network.security_groups():
                        _LOGGER.info(
                            f"Name: {sg.name}, ID: {sg.id}, Description: {sg.description or 'No description'}"
                        )
                    return (
                        False,
                        f"Unknown security group ({security_group_name}). Check list above.",
                    )

        selected_networks = []

        if networks:
            for network in networks:
                selected_networks.append(network)

        for network_selected in selected_networks:
            network = conn.network.find_network(network_selected)

            if not network:
                _LOGGER.error(f"Unknown network ({network_selected})")

                for network in conn.network.networks():
                    _LOGGER.info(f"Name: {network.name}, ID: {network.id}")

                return False, f"Unknown network ({network_selected})"

        return True, ""

    def list_servers(
        self,
        conn: openstack.connection.Connection,
        show_all: bool = False,
        federee: Optional[str] = None,
    ):
        """List all OpenStack servers."""
        if show_all:
            _LOGGER.info("--show-all is enabled.")
        else:
            _LOGGER.info(
                "Listing only VMs created with EWC CLI. If you want to see all VMs, use --show-all flag."
            )

        # List all servers
        servers = {}

        # Build a dict of image IDs to image names
        image_map = {image.id: image.name for image in conn.compute.images()}

        for server in conn.compute.servers():
            if (
                not (
                    server.metadata.get("deployed")
                    and server.metadata.get("deployed") == "ewccli"
                )
                and not show_all
            ):
                continue

            image_id = server.image.get("id") if server.image else None
            image_name = image_map.get(image_id, "N/A") if image_id else "N/A"

            addresses = server.get("addresses")
            network_ip = {}

            if federee == Federee.EUMETSAT.value:
                if "private" in addresses:
                    for c in addresses.get("private"):
                        if c.get("OS-EXT-IPS:type"):
                            ip_type = c["OS-EXT-IPS:type"]
                            network_ip[f"private-{ip_type}"] = c.get("addr")

                if "manila-network" in addresses:
                    for c in addresses.get("manila-network"):
                        network_ip["sfs-manila-network"] = c.get("addr")

            if federee == Federee.ECMWF.value:
                for address, address_v in addresses.items():
                    network_ip[f"{address}"] = [v.get("addr") for v in address_v]

            if federee:
                networks = "\n".join([f"{n} ({v})" for n, v in network_ip.items()])
            else:
                networks = "\n".join([n for n in server.addresses])

            sec_groups = getattr(server, "security_groups", [])

            servers[server.id] = {
                "name": server.name,
                "status": server.status,
                "flavor": server.flavor["original_name"],
                "image": image_name,
                "networks": networks,
                "security-groups": ",".join(sg.get("name") for sg in sec_groups),
                "id": server.id,
            }
            _LOGGER.debug(f"{server.name} ({server.status}) - {server.id}")

        return servers

    def delete_server(
        self,
        conn: openstack.connection.Connection,
        server_name: str,
        force: bool = False,
        wait_time_s: int = 600,
        dry_run: bool = False,
    ) -> Tuple[ServerResult, str]:
        """Delete an OpenStack server.

        :param conn: The OpenStack connection
        :param server_name: The server name
        :param force: if enabled, also machine not created with the CLI will be deleted.
        :param wait_time_s: The maximum period to wait (for creation or deletion).
        :returns: False on failure
        """
        if dry_run:
            _LOGGER.warning(f"Dry run enabled. {server_name} won't be deleted.")
            return (
                ServerResult(True, False, 0),
                f"Dry run enabled. {server_name} won't be deleted.",
            )

        if force:
            _LOGGER.info("--force is enabled.")

        _LOGGER.info(f"Deleting... ({server_name})")

        # Verify if the server exists
        server_info = conn.get_server(name_or_id=server_name)

        if not server_info:
            return (
                ServerResult(True, False, 0),
                f"{server_name} VM doesn't exist on Openstack! No VM to delete.",
            )

        if not server_info.metadata.get("deployed") and not force:
            return (
                ServerResult(True, False, 0),
                "The VM was not created with ewccli therefore is not deleted automatically with this command."
                " Use --force if you want to delete it anyway.",
            )

        # Delete the instance
        # and wait for it...
        conn.compute.delete_server(server_info)

        time.sleep(10)
        # # Verify if the server exists
        # server_info = conn.get_server(name_or_id=server_name)

        # if not server_info:
        #     try:
        #         conn.compute.wait_for_delete(
        #             server_info,
        #             wait=wait_time_s
        #         )
        #     except openstack.exceptions.ResourceTimeout:
        #         return ServerResult(False, False, 1), f"ResourceTimeout/delete ({server_name})"

        return ServerResult(True, True, 0), f"({server_name}) deleted successfully."

    def remove_external_ip(
        self, conn: openstack.connection.Connection, server: Server, external_ip: str
    ):
        """Remove external IP from the machine.

        :param conn: The OpenStack connection
        :param server: Server object
        :param external_ip: The external IP
        """
        try:
            ports = list(conn.network.ports(device_id=server.id))
            server_port = ports[0]
            floating_ips = list(conn.network.ips(port_id=server_port.id))
            fip = floating_ips[0]
            _LOGGER.debug(
                f"Found floating IP {fip.floating_ip_address} on port {server_port.id}"
            )

            conn.network.update_ip(fip, port_id=None)
            _LOGGER.info(
                f"Floating IP ({fip.floating_ip_address}) detached from the machine."
            )

        except Exception as e:
            _LOGGER.error(
                f"Floating IP ({fip.floating_ip_address}) not detached from the machine due to: {e}"
            )
            return ExternalIPResult(False, False)

        return ExternalIPResult(True, True)

    def add_external_ip(
        self,
        conn: openstack.connection.Connection,
        server: Server,
        federee: str,
        dry_run: bool = False,
    ) -> Tuple[ExternalIPResult, str, Optional[str]]:
        """Add external IP to the machine.

        :param conn: The OpenStack connection
        :param server: Server object
        """
        # Check if the VM has already a floating IP
        networks_ips = {}

        if dry_run:
            return ExternalIPResult(True, False), "Dru Run. No actions.", None

        _LOGGER.info(
            f"Adding Floating IP to {server.name} server. This can take some minutes ☕️..."
        )

        if "addresses" not in server:
            return (
                ExternalIPResult(False, False),
                "addresses key is missing in server_info.",
                None,
            )

        default_network = ewc_hub_config.DEFAULT_NETWORK_MAP.get(federee)
        if federee == Federee.ECMWF.value:
            networks_identified = [n.name for n in self.list_networks(conn=conn)]
            private_network_name = [
                n for n in networks_identified if default_network in n
            ][0]
        else:
            private_network_name = default_network

        for c in server["addresses"][private_network_name]:
            if c.get("OS-EXT-IPS:type"):
                networks_ips[c["OS-EXT-IPS:type"]] = c.get("addr")

        if "floating" in networks_ips:
            floating_ip = networks_ips["floating"]
            return (
                ExternalIPResult(True, False),
                f"{server.name} machine already has floating IP {floating_ip}.",
                floating_ip,
            )

        try:
            network = conn.network.find_network(
                ewc_hub_config.DEFAULT_EXTERNAL_NETWORK_MAP.get(federee)
            )
            floating_ips = list(conn.network.ips(status="DOWN"))

            if floating_ips:
                floating_ip = floating_ips[0]
            else:
                floating_ip = conn.network.create_ip(floating_network_id=network.id)

            ports = list(conn.network.ports(device_id=server.id))
            server_port = ports[0]

            conn.network.update_ip(floating_ip, port_id=server_port.id)

        except Exception as e:
            return (
                ExternalIPResult(False, False),
                f"Floating IP was not attached to VM {server.name} due to: {e}",
                None,
            )

        return (
            ExternalIPResult(True, True),
            f"✅ Floating IP {floating_ip.floating_ip_address} assigned to server {server.name}",
            floating_ip,
        )

    def list_networks(
        self,
        conn: openstack.connection.Connection,
    ):
        """
        List all networks accessible via the OpenStack connection.
        """
        networks = conn.network.networks()  # returns a generator of Network objects
        return networks

    def remove_network(
        self, conn: openstack.connection.Connection, server: Server, network_name: str
    ):
        """Add network to the machine.

        :param conn: The OpenStack connection
        :param server: Server object
        :param network_name: name of the network
        """
        # Get the network object
        # List all interfaces (ports) attached to the server
        interfaces = list(conn.compute.server_interfaces(server))
        # Iterate over interfaces and detach the one you want
        detached = False

        for iface in interfaces:
            network = conn.network.get_network(iface.net_id)

            if network.name == network_name:
                try:
                    conn.compute.delete_server_interface(server, iface.port_id)
                    _LOGGER.info(
                        f"✅ Detached network {network.name} from server {server.name}"
                    )
                    detached = True
                    return NetworkResult(True, True)

                except Exception as e:
                    _LOGGER.error(
                        f"Network {network_name} not attached to VM {server.name} due to: {e}"
                    )
                    return NetworkResult(False, False)

        if not detached:
            _LOGGER.warning(f"{network_name} not found for server {server.name}")
            return NetworkResult(True, False)

    def create_keypair(
        self,
        conn: openstack.connection.Connection,
        keypair_name: str,
        public_key_path: Path,
        dry_run: bool = False,
    ) -> Tuple[KeyPairResult, str]:
        """Create Keypair from SSH Public key.

        :param conn: The OpenStack connection
        :param keypair_name: The keypair name
        :param public_key_path: Path to the public_key_path
        """
        if dry_run:
            return KeyPairResult(True, False)

        # Step: Upload the public key
        with open(public_key_path, "r") as key_file:
            public_key = key_file.read()

        # Check if the key already exists
        existing_key = conn.compute.find_keypair(keypair_name)

        if existing_key:
            return (
                KeyPairResult(True, False),
                f"Keypair '{keypair_name}' already exists on Openstack. Using this key to deploy the VM.",
            )
        else:
            try:
                conn.compute.create_keypair(
                    name=keypair_name,
                    public_key=public_key,
                )
                return (
                    KeyPairResult(True, True),
                    f"Keypair '{keypair_name}' created successfully. This keypair will be used to deploy the VM.",
                )
            except openstack.exceptions.HttpException as ex:
                # Something wrong creating the keypair.
                # Nothing we can do here.
                return (
                    KeyPairResult(False, False),
                    f"Failed to create keypair ({keypair_name}) due to: {ex}",
                )

    def delete_keypair(
        self,
        conn: openstack.connection.Connection,
        keypair_name: str,
        dry_run: bool = False,
    ) -> Tuple[KeyPairResult, str]:
        """
        Delete an existing keypair from OpenStack.

        :param conn: The OpenStack connection
        :param keypair_name: The name of the keypair to delete
        :param dry_run: If True, do not actually delete the keypair
        """
        if dry_run:
            _LOGGER.debug(f"[Dry Run] Would delete keypair '{keypair_name}'.")
            return (
                KeyPairResult(True, False),
                f"[Dry Run] Would delete keypair '{keypair_name}'.",
            )

        # Check if the keypair exists
        keypair = conn.compute.find_keypair(keypair_name)

        if not keypair:
            return (
                KeyPairResult(True, False),
                f"Keypair '{keypair_name}' not found. Nothing to delete.",
            )

        try:
            conn.compute.delete_keypair(keypair)
            return (
                KeyPairResult(True, True),
                f"Keypair '{keypair_name}' deleted successfully.",
            )
        except openstack.exceptions.HttpException as ex:
            return (
                KeyPairResult(False, False),
                f"Failed to delete keypair '{keypair_name}'. Due to: {ex}",
            )
