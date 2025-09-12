#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Common CRD classes."""


class GroupVersionResource:
    """
    Represents a Kubernetes GroupVersionResource (GVR) identifier.

    Attributes:
        group (str): The API group of the resource (e.g., "apps", "dns.europeanweather.cloud").
        version (str): The API version of the resource (e.g., "v1", "v1alpha1").
        resource (str): The plural name of the resource (e.g., "pods", "records").
    """
    def __init__(self, group: str, version: str, resource: str):
        self.group = group
        self.version = version
        self.resource = resource
