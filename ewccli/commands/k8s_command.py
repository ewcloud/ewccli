#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC: EWC Kubernetes."""

import yaml
import rich_click as click

from ewccli.logger import get_logger
from ewccli.configuration import config as ewc_hub_config
from ewccli.backends.kubernetes.CRDtemplates.clustercrd import ClusterGVR
from ewccli.commands.commons import CommonBackendContext
from ewccli.commands.commons import login_options
from ewccli.commands.commons import split_config_name
from ewccli.backends.kubernetes.backend_k8s import KubernetesBackend
from ewccli.commands.commons import show_objects
from ewccli.utils import load_cli_config


_LOGGER = get_logger(__name__)

cb_context = click.make_pass_decorator(CommonBackendContext, ensure=True)


@click.group(name='k8s')
@cb_context
@login_options
def ewc_k8s_command(ctx, config_name):
    """EWC Kubernetes commands group."""
    if config_name:
        region, tenant_name = split_config_name(config_name=config_name)
        ctx.cli_config = load_cli_config(tenant_name=tenant_name, region=region)

    token = ctx.cli_config["token"]
    region = ctx.cli_config["region"]
    ctx.k8s_backend = KubernetesBackend(
        token=token,
        host=ewc_hub_config.DEFAULT_KUBERNETES_SERVER.get(region)
    )


@ewc_k8s_command.command()
@cb_context
def get(ctx):
    """Get list of Clusters."""
    namespace = ctx.cli_config["tenant_name"]

    plural = ClusterGVR.resource

    objects = ctx.k8s_backend.list_custom_resources(
        group=ClusterGVR.group, version=ClusterGVR.version, namespace=namespace, plural=plural
    )

    if not objects:
        click.echo(f"No {plural} found.")
        return

    show_objects(
        title=f"{ClusterGVR.resource}", objects=objects, plural=plural, namespace=namespace
    )


@ewc_k8s_command.command()
@cb_context
@click.argument("cluster_name", type=str)
def delete(ctx, cluster_name: str):
    """
    Delete a Cluster.

    Example:
         ewc k8s delete clusterName
    """
    # Add your backend logic here
    namespace = ctx.cli_config["tenant_name"]
    ctx.k8s_backend.delete_custom_resource(
        group=ClusterGVR.group,
        version=ClusterGVR.version,
        namespace=namespace,
        plural=ClusterGVR.resource,  # this must match the CRD's `spec.names.plural`
        name=cluster_name,
    )

@ewc_k8s_command.command()
@cb_context
def kubeconfig(ctx):
    """
    Get kubeconfig.
    """
    # Add your backend logic here
    namespace = ctx.cli_config["tenant_name"]


@ewc_k8s_command.command()
@cb_context
@click.option("--cluster-name", required=True, help="The name of the Kubernetes cluster.")
@click.option("--k8s-version", required=False, help="The Kubernetes version to deploy.")
@click.option("--node-count", required=False, type=int, help="Number of worker nodes in the cluster.")
@click.option("--node-size", required=False, help="Size/flavor of the worker nodes.")
@click.option("--region", required=False, help="The region where the cluster will be deployed.")
@click.option("--dry-run", is_flag=True, help="Simulate creation without applying")
def create(  # noqa: CFQ002
    ctx,
    cluster_name: str,
    k8s_version: str,
    node_count: int,
    node_size: str,
    region: str,
    dry_run: bool,
):
    """Create a K8s cluster.
Example:
ewc k8s create \
--cluster-name mycluster

    """
    click.echo("Creating K8s cluster with:")
    click.echo(f"- Cluster Name: {cluster_name}")

    if dry_run:
        click.echo("⚠️ Dry run mode enabled. Nothing will be applied.")

    namespace = ctx.cli_config["tenant_name"]
    site_name = ctx.cli_config["region"]

    # Mandatory
    spec = {
        "siteName": site_name,
        "clusterName": cluster_name,
    }

    if k8s_version:
        spec["kubernetesVersion"] = k8s_version

    if node_count:
        spec["nodeCount"] = node_count

    if node_size:
        spec["nodeSize"] = node_size

    if region:
        spec["region"] = region

    crd_config = {
        "apiVersion": f"{ClusterGVR.group}/{ClusterGVR.version}",
        "kind": f"ewcCluster",
        "metadata": {"name": cluster_name, "namespace": namespace},
        "spec": spec,
    }

    if dry_run:
        click.echo(yaml.safe_dump(crd_config, sort_keys=False))
    else:
        # Add your backend logic here
        ctx.k8s_backend.create_custom_resource(
            group=ClusterGVR.group,
            version=ClusterGVR.version,
            namespace=namespace,
            plural=ClusterGVR.resource,  # this must match the CRD's `spec.names.plural`
            body=crd_config,
        )
