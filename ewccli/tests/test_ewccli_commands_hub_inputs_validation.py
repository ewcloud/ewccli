#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC hub command inputs validation."""

import pytest
from pydantic import BaseModel

from ewccli.commands.hub.hub_utils import prepare_missing_inputs_error_message
from ewccli.commands.hub.hub_command import _validate_item_input_types
from ewccli.commands.hub.hub_command import _validate_required_inputs



# ---------------------
# Pydantic Models for Tests
# ---------------------

class ItemSchemaEntry(BaseModel):
    """Represents one schema entry specifying the name of the field and the expected type."""
    name: str
    type: str


# Realistic valid inputs
@pytest.fixture
def valid_inputs() -> dict:
    """Returns a valid set of IPA configuration inputs for testing."""
    return {
        "password_allowed_ip_ranges": ["10.0.0.0/24", "192.168.1.0/24"],
        "ipa_client_hostname": "fra-new-test",
        "ipa_server_hostname": "ipa",
        "ipa_admin_username": "admintest",
        "ipa_domain": "testfra.ewc",
        "ipa_admin_password": "wsdsdsdsd",
    }


# Realistic schema
@pytest.fixture
def item_schema() -> list:
    """Returns a list of schema entries corresponding to the IPA inputs."""
    entries = [
        ItemSchemaEntry(name="password_allowed_ip_ranges", type="List[str]"),
        ItemSchemaEntry(name="ipa_client_hostname", type="str"),
        ItemSchemaEntry(name="ipa_domain", type="str"),
        ItemSchemaEntry(name="ipa_admin_password", type="str"),
        ItemSchemaEntry(name="ipa_admin_username", type="str"),
        ItemSchemaEntry(name="ipa_server_hostname", type="str"),
    ]
    return [e.model_dump() for e in entries]

# -----------------------------
# Tests
# -----------------------------

@pytest.mark.parametrize(
    "field,value",
    [
        ("password_allowed_ip_ranges", [123]),  # should be List[str]
        ("ipa_client_hostname", 456),           # should be str
        ("ipa_domain", 789),                    # should be str
        ("ipa_admin_password", True),           # should be str
        ("ipa_admin_username", []),             # should be str
        ("ipa_server_hostname", {}),            # should be str
    ],
)
def test_invalid_inputs_return_error(item_schema, valid_inputs, field, value):
    """Test that invalid inputs return an error message string."""
    invalid_data = valid_inputs.copy()
    invalid_data[field] = value
    result = _validate_item_input_types(invalid_data, item_schema)
    
    # The function should return a non-empty string containing the field name
    assert result != ""
    assert field in result


def test_none_schema_returns_empty_string(valid_inputs):
    """Test that passing None as the schema returns empty string without error."""
    assert _validate_item_input_types(valid_inputs, None) == ""


def test_none_parsed_inputs_returns_empty_string(item_schema):
    """Test that passing None as parsed_inputs returns an empty string."""
    result = _validate_item_input_types(None, item_schema)
    assert result == ""


# Sample required inputs definition
REQUIRED_INPUTS = [
    {'name': 'ipa_client_hostname', 'type': 'str'},
    {'name': 'ipa_domain', 'type': 'str'},
    {'name': 'ipa_admin_password', 'type': 'str'}
]

def test_no_required_inputs():
    """If no required inputs are defined, should return an empty list."""
    result = _validate_required_inputs(parsed_inputs={}, required_item_inputs=[])
    assert result == []


def test_all_required_inputs_provided():
    """Should return empty list when all required inputs are provided."""
    parsed_inputs = {
        'ipa_client_hostname': 'fra-new-test',
        'ipa_domain': 'testfra.ewc',
        'ipa_admin_password': 'secret123'
    }
    missing = _validate_required_inputs(parsed_inputs=parsed_inputs, required_item_inputs=REQUIRED_INPUTS)
    assert missing == []


def test_some_required_inputs_missing():
    """Should return list of missing required inputs."""
    parsed_inputs = {
        'ipa_client_hostname': 'fra-new-test'
    }
    missing = _validate_required_inputs(parsed_inputs=parsed_inputs, required_item_inputs=REQUIRED_INPUTS)
    assert missing == ['ipa_domain', 'ipa_admin_password']


def test_no_inputs_provided():
    """If parsed_inputs is None, all required keys are missing."""
    missing = _validate_required_inputs(parsed_inputs=None, required_item_inputs=REQUIRED_INPUTS)
    assert missing == ['ipa_client_hostname', 'ipa_domain', 'ipa_admin_password']


def test_prepare_missing_inputs_error_message():
    """Test helper function generates correct message."""
    missing_keys = ['ipa_domain', 'ipa_admin_password']
    message = prepare_missing_inputs_error_message(missing_keys)
    expected = "Missing 2 required item input(s):\n- ipa_domain\n- ipa_admin_password"
    assert message == expected
