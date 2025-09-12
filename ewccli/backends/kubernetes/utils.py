#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Helpers methods for Kubernetes backend."""


def get_status_from_conditions(conditions: list) -> str:
    """
    Extract a human-readable status from conditions list.

    :param conditions: List of condition dicts from CR status.
    :return: Status string, e.g. "Ready: True" or "Synced: True"
    """
    if not conditions:
        return "N/A"
    # Try to find Ready condition first
    ready = next((c for c in conditions if c.get("type") == "Ready"), None)
    if ready:
        return f"{ready.get('type')}: {ready.get('status')}"
    # Otherwise fallback to first condition
    first = conditions[0]
    return f"{first.get('type')}: {first.get('status')}"


def get_reason_from_conditions(conditions: list) -> str:
    """
    Extract the reason from the 'Ready' condition if available,
    otherwise fallback to the first condition's reason.

    :param conditions: List of condition dicts from CR status.
    :return: Reason string, or 'N/A' if not found.
    """
    if not conditions:
        return "N/A"

    # 1. Check if 'Ready' condition exists and has a reason
    ready = next((c for c in conditions if c.get("type") == "Ready"), None)
    if ready and ready.get("reason"):
        return ready["reason"]

    # 2. Look for first condition with status 'False'
    failed = next((c for c in conditions if c.get("status") == "False" and c.get("reason")), None)
    if failed:
        return failed["reason"]

    # 3. Fallback to first condition's reason
    return conditions[0].get("reason", "N/A")
