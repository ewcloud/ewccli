#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


from typing import Optional, List, Dict

from pydantic import BaseModel, Field


class Address(BaseModel):
    """
    Pydantic model representing a single IP address entry for a server.

    Attributes:
        addr (str): The IP address.
        OS_EXT_IPS_type (Optional[str]): The type of IP, e.g., "fixed" or "floating".
    """
    addr: str
    OS_EXT_IPS_type: Optional[str] = Field(None, alias="OS-EXT-IPS:type")


class SecurityGroup(BaseModel):
    """Represents a security group associated with a server."""
    name: str


class ServerInfo(BaseModel):
    """Represents the server information required for deployed VM info extraction."""
    id: str
    name: str
    flavor: Dict[str, str]
    key_name: str
    status: str
    addresses: Optional[Dict[str, List[Address]]] = {}
    security_groups: List[SecurityGroup] = []

