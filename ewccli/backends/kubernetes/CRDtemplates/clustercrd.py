#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Cluster CRD classes."""

from dataclasses import dataclass, field
from typing import Optional

from ewccli.backends.kubernetes.CRDtemplates.commoncrd import GroupVersionResource


@dataclass
class ClusterSpec:
    """
    Specification for a DNS record in the custom resource.

    Attributes:
        siteName (str): The name of the site where this Kubernetes cluster will be deployed.
        clusterName (str): The name of the Kubernetes cluster.
        kubernetesVersion (Optional[str]): The Kubernetes version to deploy.
        nodeCount (Optional[int]): Number of worker nodes in the cluster.
        nodeSize (Optional[str]): Size/flavor of the worker nodes.
        region (Optional[str]): The region where the cluster will be deployed.
    """
    siteName: str
    clusterName: str
    kubernetesVersion: Optional[str] = None
    nodeCount: Optional[int] = None
    nodeSize: Optional[str] = None
    region: Optional[str] = None


@dataclass
class Metadata:
    """
    Metadata for the custom resource, including name, namespace, and optional labels.

    Attributes:
        name (str): Name of the custom resource.
        namespace (Optional[str]): Kubernetes namespace (optional).
        labels (Optional[dict]): Dictionary of key-value labels.
    """
    name: str
    namespace: Optional[str] = None
    labels: Optional[dict] = field(default_factory=dict)


@dataclass
class ClusterConfig:
    """
    Represents the full Cluster record custom resource definition.

    Attributes:
        apiVersion (str): API version of the custom resource.
        kind (str): Kind of the resource (e.g., "Record").
        metadata (Metadata): Resource metadata.
        spec (RecordSpec): Specification of the cluster.
    """
    apiVersion: str
    kind: str
    metadata: Metadata
    spec: ClusterSpec


ClusterGVR = GroupVersionResource(
    group="k8s.europeanweather.cloud",
    version="v1alpha1",
    resource="ewcclusters"
)
