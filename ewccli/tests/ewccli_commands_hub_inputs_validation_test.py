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
from ewccli.commands.hub.hub_command import _validate_item_inputs_format


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
        ("password_allowed_ip_ranges", [123]),         # List[str] expected
        ("password_allowed_ip_ranges", [None]),        # None not allowed inside list
        ("password_allowed_ip_ranges", "not-a-list"),  # wrong type
        ("ipa_client_hostname", 456),                  # should be str
        ("ipa_domain", True),                          # should be str
        ("ipa_admin_password", {}),                    # should be str
        ("ipa_admin_username", []),                    # should be str
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
    assert "expected type" in result

# ------------------------------------------------------------
# Valid list and Optional inputs
# ------------------------------------------------------------

def test_list_of_strings_valid(item_schema, valid_inputs):
    modified = valid_inputs.copy()
    modified["password_allowed_ip_ranges"] = ["a", "b"]

    result = _validate_item_input_types(modified, item_schema)
    assert result == ""


def test_list_empty_valid(item_schema, valid_inputs):
    modified = valid_inputs.copy()
    modified["password_allowed_ip_ranges"] = []

    result = _validate_item_input_types(modified, item_schema)
    assert result == ""


def test_optional_list_none_valid():
    schema = [{"name": "foo", "type": "Optional[List[str]]"}]
    parsed = {"foo": None}

    result = _validate_item_input_types(parsed, schema)
    assert result == ""


def test_none_schema_returns_empty_string(valid_inputs):
    """Test that passing None as the schema returns empty string without error."""
    assert _validate_item_input_types(valid_inputs, None) == ""


def test_none_parsed_inputs_returns_empty_string(item_schema):
    """Test that passing None as parsed_inputs returns an empty string."""
    assert _validate_item_input_types(None, item_schema) == ""

# ------------------------------------------------------------
# Literal parsing cases
# ------------------------------------------------------------

def test_unquoted_list_string_is_invalid():
    """
    Your implementation treats a quoted list string (\"['a','b']\") as invalid for List[str].
    """
    parsed_inputs = {"list_key": "['a','b']"}
    schema = [{"name": "list_key", "type": "List[str]"}]

    result = _validate_item_input_types(parsed_inputs, schema)

    assert result != ""
    assert "list_key" in result
    assert "expected type: List[str]" in result


def test_real_unquoted_list_failure():
    """
    Simulate user passing:
        --item-input list_key=[a,b]
    which cannot be literal_eval'ed and becomes a raw string "[a,b]".
    """

    parsed_inputs = {"list_key": "[a,b]"}  # cannot literal_eval correctly
    schema = [{"name": "list_key", "type": "List[str]"}]

    result = _validate_item_input_types(parsed_inputs, schema)

    assert result != ""
    assert "expected type: List[str]" in result


def test_parsing_of_literal_eval_strings_fails_for_list():
    """
    literal_eval is not used in your real implementation for list parsing.
    The string \"['a','b']\" is invalid.
    """
    ctx_values = [("names", "['a','b']")]

    parsed = dict(ctx_values)

    schema = [{"name": "names", "type": "List[str]"}]
    result = _validate_item_input_types(parsed, schema)

    assert result != ""


# ------------------------------------------------------------
# Required inputs tests
# ------------------------------------------------------------

# Sample required inputs definition
REQUIRED_INPUTS = [
    {"name": "ipa_client_hostname", "type": "str"},
    {"name": "ipa_domain", "type": "str"},
    {"name": "ipa_admin_password", "type": "str"},
]


def test_no_required_inputs():
    """If no required inputs are defined, should return an empty list."""
    assert _validate_required_inputs(parsed_inputs={}, required_item_inputs=[]) == []


def test_all_required_inputs_provided():
    """Should return empty list when all required inputs are provided."""
    parsed_inputs = {
        "ipa_client_hostname": "fra-new-test",
        "ipa_domain": "testfra.ewc",
        "ipa_admin_password": "secret123",
    }
    missing = _validate_required_inputs(
        parsed_inputs=parsed_inputs, required_item_inputs=REQUIRED_INPUTS
    )
    assert missing == []


def test_some_required_inputs_missing():
    """Should return list of missing required inputs."""
    parsed_inputs = {"ipa_client_hostname": "fra-new-test"}
    missing = _validate_required_inputs(
        parsed_inputs=parsed_inputs, required_item_inputs=REQUIRED_INPUTS
    )
    assert missing == ["ipa_domain", "ipa_admin_password"]


def test_no_inputs_provided():
    """If parsed_inputs is None, all required keys are missing."""
    missing = _validate_required_inputs(
        parsed_inputs=None, required_item_inputs=REQUIRED_INPUTS
    )
    assert missing == ["ipa_client_hostname", "ipa_domain", "ipa_admin_password"]


def test_prepare_missing_inputs_error_message():
    """Test helper function generates correct message."""
    missing_keys = ["ipa_domain", "ipa_admin_password"]
    message = prepare_missing_inputs_error_message(missing_keys)
    expected = "Missing 2 required item input(s):\n- ipa_domain\n- ipa_admin_password"
    assert message == expected


# -------------------------------------------------
# NEW TESTS for empty values in the input variables
# -------------------------------------------------

def test_empty_string_value_is_accepted(item_schema, valid_inputs):
    """Ensure key="" is treated as valid (empty string), not an error."""
    modified = valid_inputs.copy()
    modified["ipa_domain"] = ""   # empty string allowed

    result = _validate_item_input_types(modified, item_schema)
    assert result == ""


def test_empty_string_does_not_count_as_missing():
    parsed = {
        "ipa_client_hostname": "",
        "ipa_domain": "",
        "ipa_admin_password": "",
    }
    missing = _validate_required_inputs(parsed, REQUIRED_INPUTS)

    assert missing == []


def test_empty_string_after_literal_eval(item_schema, valid_inputs):
    parsed = valid_inputs.copy()
    parsed["ipa_domain"] = ""  # Only change domain to empty string

    result = _validate_item_input_types(parsed, item_schema)

    assert result == ""
# ------------------------------------------------------------
# Missing message formatting
# ------------------------------------------------------------

def test_prepare_missing_inputs_error_message():
    missing = ["ipa_domain", "ipa_admin_password"]
    msg = prepare_missing_inputs_error_message(missing)
    assert msg == "Missing 2 required item input(s):\n- ipa_domain\n- ipa_admin_password"
