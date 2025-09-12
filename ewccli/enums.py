#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Enums for EWC CLI."""

from enum import Enum


class Federee(Enum):
    """EWC Federee."""

    ECMWF = "ECMWF"
    EUMETSAT = "EUMETSAT"


class HubItemTechnologyAnnotation(Enum):
    """EWC Hub Item Technology Annotation (deployable)."""

    ANSIBLE = "Ansible Playbook"
    TERRAFORM = "Terraform Module"


class HubItemCategoryAnnotation(Enum):
    """EWC Hub Item Category Annotation."""

    GPU_ACCELERATED = "GPU-accelerated"


class HubItemOherAnnotation(Enum):
    """EWC Hub Item Other Annotation."""

    EWCCLI_COMPATIBLE = "EWCCLI-compatible"


class HubItemCLIKeys(Enum):
    """EWC Hub Item EWCCLI specific keys under `ewccli`."""

    ROOT = "ewccli"
    INPUTS = "inputs"
    DEFAULT_IMAGE_NAME = "defaultImageName"
    DEFAULT_SECURITY_GROUPS = "defaultSecurityGroups"
    ITEM_PATH_TO_MAIN_FILE = "pathToMainFile"
    ITEM_PATH_TO_REQUIREMENTS_FILE = "pathToRequirementsFile"
    EXTERNAL_IP = "externalIP"
