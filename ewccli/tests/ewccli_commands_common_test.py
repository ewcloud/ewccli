#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025, 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Tests for EWC commands common methods."""

from __future__ import annotations

import pytest
from rich.console import Console
from rich.table import Table

from ewccli.commands.commons import (
    show_item_table,
)


@pytest.fixture
def console_capture(monkeypatch):
    """
    Capture Rich console output so we can assert on the rendered table.
    """
    console = Console(record=True)
    monkeypatch.setattr("ewccli.commands.commons.console", console)
    return console


@pytest.fixture
def sample_hub_item():
    return {
        "name": "demo-item",
        "version": "1.0.0",
        "summary": "A demo item",
        "maintainers": [
            {"name": "Alice", "url": "https://example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ],
        "annotations": {
            "category": "test",
            "tier": "gold",
        },
        "description": "This is a test description.",
        "ewccli": {
            "inputs": [
                {
                    "name": "param1",
                    "type": "string",
                    "description": "First parameter",
                    "default": "abc",
                },
                {
                    "name": "param2",
                    "type": "int",
                    "description": "Second parameter",
                },
            ],
            "defaultImageName": "ubuntu:22.04",
            "defaultSecurityGroups": ["sg-123", "sg-456"],
        },
    }


def test_show_item_table_renders_basic_fields(console_capture, sample_hub_item):
    show_item_table(sample_hub_item)

    output = console_capture.export_text()

    assert "demo-item EWC Item Details" in output
    assert "name" in output
    assert "demo-item" in output
    assert "version" in output
    assert "1.0.0" in output
    assert "summary" in output
    assert "A demo item" in output


def test_show_item_table_renders_maintainers(console_capture, sample_hub_item):
    show_item_table(sample_hub_item)
    output = console_capture.export_text()

    assert "Alice" in output
    assert "https://example.com" in output
    assert "Bob" in output
    assert "bob@example.com" in output


def test_show_item_table_renders_annotations(console_capture, sample_hub_item):
    show_item_table(sample_hub_item)
    output = console_capture.export_text()

    assert "category" in output
    assert "test" in output
    assert "tier" in output
    assert "gold" in output


def test_show_item_table_renders_description(console_capture, sample_hub_item):
    show_item_table(sample_hub_item)
    output = console_capture.export_text()

    assert "This is a test description." in output


def test_show_item_table_renders_inputs(console_capture, sample_hub_item):
    show_item_table(sample_hub_item)
    output = console_capture.export_text()

    # param1 has default → optional
    assert "(optional)" in output
    assert "param1" in output
    assert "(default: abc)" in output

    # param2 has no default → mandatory
    assert "(mandatory)" in output
    assert "param2" in output


def test_show_item_table_renders_deploy_command(console_capture, sample_hub_item):
    show_item_table(sample_hub_item)
    output = console_capture.export_text()

    assert "ewc hub deploy demo-item" in output
    # param2 is mandatory → must appear in deploy command
    assert "--item-inputs param2" in output


def test_show_item_table_renders_defaults(console_capture, sample_hub_item):
    show_item_table(sample_hub_item)
    output = console_capture.export_text()

    assert "Image Name: ubuntu:22.04" in output
    assert "Security Group/s: sg-123,sg-456" in output
