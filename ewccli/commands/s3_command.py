#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC: EWC S3."""

import yaml
import rich_click as click

from ewccli.logger import get_logger
from ewccli.configuration import config as ewc_hub_config
from ewccli.backends.kubernetes.CRDtemplates.bucketccrd import BucketGVR
from ewccli.commands.commons import CommonBackendContext
from ewccli.backends.kubernetes.backend_k8s import KubernetesBackend
from ewccli.commands.commons import show_objects


_LOGGER = get_logger(__name__)

cb_context = click.make_pass_decorator(CommonBackendContext, ensure=True)


@click.group(name='s3')
@cb_context
def ewc_s3_command(ctx):
    """EWC S3 commands group."""
    token = ctx.cli_config["token"]
    region = ctx.cli_config["region"]
    ctx.k8s_backend = KubernetesBackend(
        token=token, host=ewc_hub_config.DEFAULT_KUBERNETES_SERVER.get(region)
    )


@click.group(name='bucket')
def ewc_s3_bucket_command():
    """EWC S3 bucket commands group."""


@ewc_s3_bucket_command.command()
@cb_context
def get(ctx):
    """Get list of Buckets."""
    namespace = ctx.cli_config["tenant_name"]

    plural = BucketGVR.resource

    objects = ctx.k8s_backend.list_custom_resources(
        group=BucketGVR.group, version=BucketGVR.version, namespace=namespace, plural=plural
    )

    if not objects:
        click.echo(f"No {plural} found.")
        return

    show_objects(
        title=f"{BucketGVR.resource}", objects=objects, plural=plural, namespace=namespace
    )


@ewc_s3_bucket_command.command()
@cb_context
@click.argument("bucket-name", type=str)
def delete(ctx, bucket_name: str):
    """
    Delete an S3 bucket.

    Example:
         ewc S3 bucket delete BUCKET_NAME
    """
    # Add your backend logic here
    namespace = ctx.cli_config["tenant_name"]
    ctx.k8s_backend.delete_custom_resource(
        group=BucketGVR.group,
        version=BucketGVR.version,
        namespace=namespace,
        plural=BucketGVR.resource,  # this must match the CRD's `spec.names.plural`
        name=bucket_name,
    )


@ewc_s3_bucket_command.command()
@cb_context
@click.option("--bucket-name", required=True, help="The name of the bucket.")
@click.option("--access-id", required=True, help="Access ID of the S3 credentials.")
@click.option(
    "--write-access-id",
    multiple=True,
    type=str,
    help="ID(s) that have write access to the S3 bucket (can be passed multiple times)"
)
@click.option(
    "--write-access-refs-id",
    multiple=True,
    type=str,
    help="Reference ID(s) that have write access to the S3 bucket (can be passed multiple times)"
)
@click.option(
    "--read-access-id",
    multiple=True,
    type=str,
    help="ID(s) that have read access to the S3 bucket (can be passed multiple times)"
)
@click.option(
    "--read-access-refs-id",
    multiple=True,
    type=str,
    help="Reference ID(s) that have read access to the S3 bucket (can be passed multiple times)"
)
@click.option("--geo-enabled", is_flag=True, help="Enable georedundancy")
@click.option("--dry-run", is_flag=True, help="Simulate creation without applying")
def create(  # noqa: CFQ002
    ctx,
    bucket_name: str,
    access_id: str,
    write_access_id: tuple,
    write_access_refs_id: tuple,
    read_access_id: tuple,
    read_access_refs_id: tuple,
    geo_enabled: bool,
    dry_run: bool,
):
    """Create an S3 bucket.
Example:
ewc s3 bucket create \
--bucket-name mycluster
--access-id accessID

    """
    click.echo("Creating S3 bucket with:")
    click.echo(f"- Bucket Name: {bucket_name}")

    if dry_run:
        click.echo("⚠️ Dry run mode enabled. Nothing will be applied.")

    namespace = ctx.cli_config["tenant_name"]
    site_name = ctx.cli_config["region"]

    # Mandatory
    spec = {
        "siteName": site_name,
        "bucketName": bucket_name,
        "owner": access_id
    }

    # Optional
    if write_access_id:
        spec["writeAccessIds"] = list(write_access_id)

    if write_access_refs_id:
        spec["writeAccessRefsIds"] = list(write_access_refs_id)

    if read_access_id:
        spec["readAccessIds"] = list(read_access_id)

    if read_access_refs_id:
        spec["readAccessRefsIds"] = list(read_access_refs_id)

    if geo_enabled:
        spec["georedundancy"] = {
            "enabled": geo_enabled
        }

    crd_config = {
        "apiVersion": f"{BucketGVR.group}/{BucketGVR.version}",
        "kind": f"Bucket",
        "metadata": {"name": bucket_name, "namespace": namespace},
        "spec": spec,
    }

    if dry_run:
        click.echo(yaml.safe_dump(crd_config, sort_keys=False))
    else:
        # Add your backend logic here
        ctx.k8s_backend.create_custom_resource(
            group=BucketGVR.group,
            version=BucketGVR.version,
            namespace=namespace,
            plural=BucketGVR.resource,  # this must match the CRD's `spec.names.plural`
            body=crd_config,
        )


@click.group(name='credentials')
@cb_context
def ewc_s3_credentials_command():
    """EWC S3 credentials commands group."""


ewc_s3_command.add_command(ewc_s3_bucket_command)
ewc_s3_command.add_command(ewc_s3_credentials_command)
