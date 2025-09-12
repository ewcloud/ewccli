#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""DNS CRD classes."""

from dataclasses import dataclass, field
from typing import List, Optional

from ewccli.backends.kubernetes.CRDtemplates.commoncrd import GroupVersionResource


@dataclass
class GeoRedundancy:
    """
    Represents georedundancy configuration for a DNS record.

    Attributes:
        enabled (bool): Whether georedundancy is enabled.
        healthEndpoint (str): The health check endpoint path.
        ssl (bool): Whether to use HTTPS for health checks.
    """
    enabled: bool
    healthEndpoint: str
    ssl: bool


@dataclass
class RecordSpec:
    """
    Specification for a DNS record in the custom resource.

    Attributes:
        siteName (str): Name of the site the record belongs to.
        domainName (str): The DNS domain associated with the record.
        recordName (str): Name of the specific DNS record.
        recordType (Optional[str]): Type of DNS record (e.g., A, CNAME, TXT).
        records (tuple): Comma separated DNS record.
        ttl (Optional[int]): Time to live for the DNS record in seconds.
        georedundancy (Optional[GeoRedundancy]): Optional georedundancy settings.
    """
    siteName: str
    domainName: str
    recordName: str
    records: List[str]
    recordType: Optional[str] = None
    ttl: Optional[int] = None
    georedundancy: Optional[GeoRedundancy] = None


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
class RecordConfig:
    """
    Represents the full DNS record custom resource definition.

    Attributes:
        apiVersion (str): API version of the custom resource.
        kind (str): Kind of the resource (e.g., "Record").
        metadata (Metadata): Resource metadata.
        spec (RecordSpec): Specification of the DNS record.
    """
    apiVersion: str
    kind: str
    metadata: Metadata
    spec: RecordSpec


RecordGVR = GroupVersionResource(
    group="dns.europeanweather.cloud",
    version="v1alpha1",
    resource="records"
)
