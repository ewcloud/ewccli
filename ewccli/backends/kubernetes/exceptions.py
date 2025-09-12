#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Exceptions class for Kubernetes backend."""

class ResourceAlreadyExistsError(Exception):
    """Exception raised when the resource already exists in the cluster."""
