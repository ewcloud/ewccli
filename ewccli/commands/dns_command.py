#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC: EWC DNS."""

import yaml
import rich_click as click

from ewccli.logger import get_logger
from ewccli.configuration import config as ewc_hub_config
from ewccli.backends.kubernetes.CRDtemplates.dnscrd import RecordGVR
from ewccli.commands.commons import CommonBackendContext
from ewccli.backends.kubernetes.backend_k8s import KubernetesBackend
from ewccli.commands.commons import show_objects, describe_object


_LOGGER = get_logger(__name__)

cb_context = click.make_pass_decorator(CommonBackendContext, ensure=True)


@click.group(name="dns")
@cb_context
def ewc_dns_command(ctx):
    """EWC DNS commands group."""
    token = ctx.cli_config["token"]
    region = ctx.cli_config["region"]
    ctx.k8s_backend = KubernetesBackend(
        token=token, host=ewc_hub_config.DEFAULT_KUBERNETES_SERVER.get(region)
    )


@ewc_dns_command.command()
@cb_context
@click.argument("record_name", type=str)
def delete(ctx, record_name: str):
    """
    Delete a DNS record.

    Example:
         ewc dns delete myrecord
    """
    # Add your backend logic here
    namespace = ctx.cli_config["tenant_name"]
    ctx.k8s_backend.delete_custom_resource(
        group=RecordGVR.group,
        version=RecordGVR.version,
        namespace=namespace,
        plural=RecordGVR.resource,  # this must match the CRD's `spec.names.plural`
        name=record_name,
    )


@ewc_dns_command.command()
@cb_context
def get(ctx):
    """Get list of DNS records."""
    namespace = ctx.cli_config["tenant_name"]
    plural = RecordGVR.resource

    objects = ctx.k8s_backend.list_custom_resources(
        group=RecordGVR.group,
        version=RecordGVR.version,
        namespace=namespace,
        plural=plural
    )

    show_objects(
        title=f"DNS {plural}", objects=objects, plural=plural, namespace=namespace
    )


@ewc_dns_command.command()
@cb_context
@click.argument("record_name", type=str)
def describe(ctx, record_name: str):
    """Describe a DNS record."""
    namespace = ctx.cli_config["tenant_name"]
    plural = RecordGVR.resource

    object = ctx.k8s_backend.describe_custom_resource(
        name=record_name,
        group=RecordGVR.group,
        version=RecordGVR.version,
        namespace=namespace,
        plural=plural
    )
    describe_object(object)


@ewc_dns_command.command()
@cb_context
@click.option("--domain-name", required=True, help="Domain name")
@click.option("--record-name", required=True, help="Record name")
@click.option(
    "--records",
    multiple=True,
    required=True,
    help="Record values (can be passed multiple times)",
)
@click.option(
    "--ttl", default=300, show_default=True, type=int, help="Time to live in seconds"
)
@click.option(
    "--record-type",
    default="A",
    show_default=True,
    type=click.Choice(["A", "AAAA", "CNAME", "TXT"], case_sensitive=False),
    help="Record type",
)
@click.option("--geo-enabled", is_flag=True, help="Enable georedundancy")
@click.option(
    "--health-endpoint",
    default="/",
    show_default=True,
    help="Health endpoint for geo redundancy",
)
@click.option(
    "--geo-ssl",
    is_flag=True,
    help="Use HTTPS for health checks",
)
# @click.option(
#     "-f", "--file", type=click.Path(exists=True), help="YAML file to load record spec"
# )
# @click.option(
#     "-o",
#     "--output",
#     type=click.Choice(["yaml", "json", "table"], case_sensitive=False),
#     help="Output format",
# )
@click.option("--dry-run", is_flag=True, help="Simulate creation without applying")
def create(  # noqa: CFQ002
    ctx,
    domain_name,
    record_name,
    records,
    record_type: str,
    ttl: int,
    health_endpoint: str,
    geo_enabled: bool = False,
    geo_ssl: bool = False,
    # file,
    # output,
    dry_run: bool = False,
):
    """Create a DNS record.
Example:
ewc dns create \
--domain-name example.com \
--record-name www \
--records 1.2.3.4,1.2.3.5

    """
    normalized_records = []
    for r in records:
        normalized_records.extend([val.strip() for val in r.split(",") if val.strip()])
    click.echo("Creating DNS record with:")
    click.echo(f"- Domain: {domain_name}")
    click.echo(f"- Record: {record_name}")
    click.echo(f"- Values: {normalized_records}")
    click.echo(f"- TTL: {ttl}, Type: {record_type}")

    if geo_enabled:
        click.echo(
            f"- Geo enabled at {health_endpoint} using {'HTTPS' if geo_ssl else 'HTTP'}"
        )

    # if file:
    #     click.echo(f"- Loading spec from file: {file}")

    if dry_run:
        click.echo("⚠️ Dry run mode enabled. Nothing will be applied.")

    namespace = ctx.cli_config["tenant_name"]
    region = ctx.cli_config["region"]

    dns_record_config = {
        "apiVersion": f"{RecordGVR.group}/{RecordGVR.version}",
        "kind": "Record",
        "metadata": {"name": record_name, "namespace": namespace},
        "spec": {
            "siteName": region,
            "domainName": domain_name,
            "recordName": record_name,
            "recordType": record_type,
            "records": normalized_records,
            "ttl": ttl,
            "georedundancy": {
                "enabled": geo_enabled,
                "healthEndpoint": health_endpoint,
                "ssl": geo_ssl,
            },
        },
    }

    if dry_run:
        # click.echo(json.dumps(dns_record_config, indent=2))
        click.echo(yaml.safe_dump(dns_record_config, sort_keys=False))
    else:
        # Add your backend logic here
        ctx.k8s_backend.create_custom_resource(
            group=RecordGVR.group,
            version=RecordGVR.version,
            namespace=namespace,
            plural=RecordGVR.resource,  # this must match the CRD's `spec.names.plural`
            body=dns_record_config,
        )
