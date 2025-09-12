#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""CLI EWC Hub: EWC Hub interaction utils methods."""

from typing import Optional, List
from urllib.parse import urlparse

from rich.console import Console

from ewccli.enums import HubItemTechnologyAnnotation
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


console = Console()


def verify_item_is_deployable(item_info: dict):
    """Verify item is deployable"""
    annotations = item_info.get("annotations")
    check_deployable = 0

    if annotations:
        technology_annotations = list(annotations.get("technology").split(","))

        for tech_annotation in technology_annotations:
            if tech_annotation in [item.value for item in HubItemTechnologyAnnotation]:
                check_deployable += 1

            if check_deployable:
                break

    if not check_deployable:
        _LOGGER.warning("You selected an item that cannot be deployed. Exiting.")
        return False

    return True


def prepare_missing_inputs_error_message(missing_inputs: list[str]):
    """Prepare missing item inputs message."""
    missing_count = len(missing_inputs)
    lines = [f"Missing {missing_count} required item input(s):"]
    lines += [f"- {input_name}" for input_name in missing_inputs]

    return "\n".join(lines)


def extract_annotations(annotations: Optional[dict] = None):
    """Extract annotations from item info."""
    annotations_category: List[str] = []
    annotations_technology: List[str] = []

    if not annotations:
        return annotations_category, annotations_technology

    annotations_category = [
        c.strip() for c in annotations.get("category", "").split(",")
    ]
    annotations_technology = [
        c.strip() for c in annotations.get("technology", "").split(",")
    ]

    return annotations_category, annotations_technology
