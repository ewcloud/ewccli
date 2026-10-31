#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Shared fixtures keeping the test-suite away from the real ~/.ewccli."""

import pytest

from ewccli.configuration import config as ewc_hub_config


@pytest.fixture(autouse=True)
def temp_profiles(tmp_path, monkeypatch):
    """Redirect the profiles file into a per-test temporary directory.

    ``ewc login`` writes profiles through ``ProfileStore()``, which resolves
    its default path at call time (see ``ProfileStore.__init__``).  Patching
    the configuration here therefore sends every read and write — from the
    CLI code under test and from the tests' own cleanup — to a temp file,
    instead of leaking profiles into (and overwriting) the real
    ``~/.ewccli/profiles``.
    """
    monkeypatch.setattr(
        ewc_hub_config, "EWC_CLI_PROFILES_PATH", tmp_path / "profiles"
    )