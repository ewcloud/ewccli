#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""S3 CRD classes."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict

from ewccli.backends.kubernetes.CRDtemplates.commoncrd import GroupVersionResource


@dataclass
class BucketSpec:
    """
    Specification for a Bucket custom resource.

    Attributes:
        siteName (str): Name of the site where this bucket will be deployed.
        bucketName (str): Name of the S3 bucket.
        owner (str): Access ID of the S3 credentials (owner of the bucket).
        writeAccessIds (Optional[List[str]]): IDs that have write access to the bucket.
        writeAccessRefsIds (Optional[List[str]]): References to IDs with write access.
        readAccessIds (Optional[List[str]]): IDs that have read access to the bucket.
        readAccessRefsIds (Optional[List[str]]): References to IDs with read access.
        georedundancy (Optional[dict]): Georedundancy configuration (enabled flag).
    """
    siteName: str
    bucketName: str
    owner: str
    writeAccessIds: Optional[List[str]] = None
    writeAccessRefsIds: Optional[List[str]] = None
    readAccessIds: Optional[List[str]] = None
    readAccessRefsIds: Optional[List[str]] = None
    georedundancy: Optional[Dict[str, bool]] = None


@dataclass
class Metadata:
    """
    Metadata for the custom resource.

    Attributes:
        name (str): Resource name (must match bucketName for S3 bucket CRs).
        namespace (str): Kubernetes namespace.
        labels (Optional[Dict]): Optional labels for resource metadata.
    """
    name: str
    namespace: str
    labels: Optional[Dict[str, str]] = field(default_factory=dict)


@dataclass
class BucketConfig:
    """
    Represents the full Bucket custom resource definition.

    Attributes:
        apiVersion (str): API version of the custom resource.
        kind (str): Kind of the resource (e.g., "Bucket").
        metadata (Metadata): Resource metadata.
        spec (BucketSpec): Bucket specification.
    """
    apiVersion: str
    kind: str
    metadata: Metadata
    spec: BucketSpec


BucketGVR = GroupVersionResource(
    group="s3.europeanweather.cloud",
    version="v1alpha1",
    resource="buckets"
)
