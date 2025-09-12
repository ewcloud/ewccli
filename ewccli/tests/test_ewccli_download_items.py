#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Test download item methods."""


import pytest
import requests

from ewccli.configuration import config as ewc_hub_config
from ewccli.utils import download_items


class DummyResponse:
    """Dummy response object for mocking requests.get."""

    def __init__(self, text: str = "dummy content", raise_exc: Exception = None):
        self.text = text
        self._raise_exc = raise_exc

    def raise_for_status(self):
        """Raise exception if configured, else succeed."""
        if self._raise_exc:
            raise self._raise_exc


@pytest.fixture
def temp_config(monkeypatch, tmp_path):
    """
    Fixture to redirect EWC config paths into a temporary directory.

    Args:
        monkeypatch: pytest fixture to patch module attributes.
        tmp_path: temporary path provided by pytest.

    Yields:
        Path: temporary config directory.
    """
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_BASE_PATH", tmp_path)
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_HUB_ITEMS_PATH", tmp_path / "items.yaml")
    monkeypatch.setattr(ewc_hub_config, "EWC_CLI_HUB_ITEMS_URL", "https://fake-url/items.yaml")
    yield tmp_path


def test_download_skips_if_file_exists_and_force_false(temp_config, monkeypatch):
    """
    Test that `download_items` does not re-download when file exists and force=False.
    """
    item_file = ewc_hub_config.EWC_CLI_HUB_ITEMS_PATH
    item_file.write_text("existing content")

    monkeypatch.setattr("requests.get", lambda *a, **kw: pytest.fail("Should not be called"))

    download_items(force=False)

    assert item_file.read_text() == "existing content"


def test_download_redownloads_if_force_true(temp_config, monkeypatch):
    """
    Test that `download_items` redownloads when force=True even if file exists.
    """
    item_file = ewc_hub_config.EWC_CLI_HUB_ITEMS_PATH
    item_file.write_text("old content")

    monkeypatch.setattr("requests.get", lambda *a, **kw: DummyResponse("new content"))

    download_items(force=True)

    assert item_file.read_text() == "new content"


def test_download_creates_new_file(temp_config, monkeypatch):
    """
    Test that `download_items` downloads and creates the file when it does not exist.
    """
    monkeypatch.setattr("requests.get", lambda *a, **kw: DummyResponse("downloaded data"))

    download_items(force=False)

    assert ewc_hub_config.EWC_CLI_HUB_ITEMS_PATH.read_text() == "downloaded data"


def test_download_handles_timeout(temp_config, monkeypatch, caplog):
    """
    Test that `download_items` logs an error when a timeout occurs.
    """
    def fake_get(*a, **kw):
        raise requests.Timeout()

    monkeypatch.setattr("requests.get", fake_get)

    download_items(force=True)

    assert "timed out" in caplog.text


def test_download_handles_request_exception(temp_config, monkeypatch, caplog):
    """
    Test that `download_items` logs an error when a RequestException occurs.
    """
    def fake_get(*a, **kw):
        raise requests.RequestException("connection error")

    monkeypatch.setattr("requests.get", fake_get)

    download_items(force=True)

    assert "connection error" in caplog.text
