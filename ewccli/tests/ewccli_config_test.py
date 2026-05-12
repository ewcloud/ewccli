#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Test config methods."""

import pytest
import click

from configparser import ConfigParser
from ewccli.profile import ProfileStore, ProfileData
from ewccli.enums import Federee


@pytest.fixture
def profile_file(tmp_path):
    """Temporary profiles file path."""
    return tmp_path / "profiles.ini"


@pytest.fixture
def ssh_paths(tmp_path):
    """Create fake SSH key files."""
    priv = tmp_path / "id_rsa"
    pub = tmp_path / "id_rsa.pub"

    priv.write_text("private")
    pub.write_text("public")

    return str(priv), str(pub)


def make_profile_data(
    federee: str,
    tenant: str,
    ssh_private: str,
    ssh_public: str,
    **extra,
) -> ProfileData:
    """Helper to build ProfileData."""
    return ProfileData(
        federee=Federee(federee),
        tenant_name=tenant,
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        **extra,
    )


# ---------------------------------------------------------------------------
# Save + Load
# ---------------------------------------------------------------------------

def test_save_and_load_profile(profile_file, ssh_paths):
    store = ProfileStore(path=profile_file)

    data = make_profile_data(
        federee="EUMETSAT",
        tenant="TeamA",
        ssh_private=ssh_paths[0],
        ssh_public=ssh_paths[1],
        token="tok1",
        application_credential_id="ID1",
        application_credential_secret="SECRET1",
        region="us-east-1",
    )

    store.save(data)

    loaded = store.load(data.profile or "EUMETSAT-TeamA")

    assert loaded.federee == data.federee
    assert loaded.tenant_name == data.tenant_name
    assert loaded.token == "tok1"
    assert loaded.application_credential_id == "ID1"
    assert loaded.application_credential_secret == "SECRET1"
    assert loaded.region == "us-east-1"
    assert loaded.ssh_private_key_path == ssh_paths[0]
    assert loaded.ssh_public_key_path == ssh_paths[1]


# ---------------------------------------------------------------------------
# Duplicate profile
# ---------------------------------------------------------------------------

def test_save_existing_profile_fails(profile_file, ssh_paths):
    store = ProfileStore(path=profile_file)

    data = make_profile_data(
        federee="EUMETSAT",
        tenant="TeamB",
        ssh_private=ssh_paths[0],
        ssh_public=ssh_paths[1],
    )

    store.save(data)

    with pytest.raises(click.Abort):
        store.save(data)


# ---------------------------------------------------------------------------
# Missing profile
# ---------------------------------------------------------------------------

def test_load_missing_profile_raises(profile_file):
    store = ProfileStore(path=profile_file)

    with pytest.raises(click.Abort):
        store.load("nonexistent")


# ---------------------------------------------------------------------------
# resolve_name
# ---------------------------------------------------------------------------

def test_resolve_name(profile_file):
    store = ProfileStore(path=profile_file)

    assert store.resolve_name("explicit", None, None) == "explicit"
    assert store.resolve_name(None, "EUMETSAT", "TeamA") == "EUMETSAT-TeamA"

    with pytest.raises(click.Abort):
        store.resolve_name(None, None, "TeamA")

    with pytest.raises(click.Abort):
        store.resolve_name(None, "EUMETSAT", None)

# ---------------------------------------------------------------------------
# ProfileData.from_section
# ---------------------------------------------------------------------------

def test_profiledata_from_section_valid(tmp_path):
    cfg = ConfigParser()
    cfg["EUMETSAT-TeamA"] = {
        "federee": "EUMETSAT",
        "tenant_name": "TeamA",
        "ssh_public_key_path": "/tmp/pub",
        "ssh_private_key_path": "/tmp/priv",
        "region": "eu-west-1",
        "token": "tok",
        "application_credential_id": "ID",
        "application_credential_secret": "SECRET",
    }

    section = cfg["EUMETSAT-TeamA"]
    data = ProfileData.from_section("EUMETSAT-TeamA", section)

    assert data.federee == Federee.EUMETSAT
    assert data.tenant_name == "TeamA"
    assert data.region == "eu-west-1"
    assert data.token == "tok"
    assert data.application_credential_id == "ID"
    assert data.application_credential_secret == "SECRET"


def test_profiledata_from_section_invalid(tmp_path):
    cfg = ConfigParser()
    cfg["bad"] = {
        "federee": "INVALID",  # not a valid enum
        "tenant_name": "TeamA",
        "ssh_public_key_path": "/tmp/pub",
        "ssh_private_key_path": "/tmp/priv",
    }

    with pytest.raises(click.ClickException):
        ProfileData.from_section("bad", cfg["bad"])


# ---------------------------------------------------------------------------
# ProfileData.to_section
# ---------------------------------------------------------------------------

def test_profiledata_to_section_roundtrip(ssh_paths):
    priv, pub = ssh_paths

    data = ProfileData(
        federee=Federee.ECMWF,
        tenant_name="Ops",
        ssh_private_key_path_to_save=priv,
        ssh_public_key_path_to_save=pub,
        region="eu-central-1",
        token="T",
        application_credential_id="ID",
        application_credential_secret="SECRET",
    )

    section = data.to_section()

    assert section["federee"] == "ECMWF"
    assert section["tenant_name"] == "Ops"
    assert section["ssh_private_key_path"] == priv
    assert section["ssh_public_key_path"] == pub
    assert section["region"] == "eu-central-1"
    assert section["token"] == "T"
    assert section["application_credential_id"] == "ID"
    assert section["application_credential_secret"] == "SECRET"


# ---------------------------------------------------------------------------
# save_default
# ---------------------------------------------------------------------------

def test_save_default_creates_only_if_missing(profile_file, ssh_paths, monkeypatch):
    monkeypatch.setattr(
        "ewccli.configuration.config.EWC_CLI_DEFAULT_PROFILE_NAME",
        "default",
    )

    store = ProfileStore(path=profile_file)

    data = ProfileData(
        federee=Federee.EUMETSAT,
        tenant_name="TeamA",
        ssh_private_key_path_to_save=ssh_paths[0],
        ssh_public_key_path_to_save=ssh_paths[1],
    )

    store.save_default(data)
    assert store.exists("default")

    # Second call must NOT overwrite
    store.save_default(data)
    assert store.exists("default")


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------

def test_list_profiles(profile_file, ssh_paths):
    store = ProfileStore(path=profile_file)

    p1 = ProfileData(
        federee=Federee.EUMETSAT,
        tenant_name="A",
        ssh_private_key_path_to_save=ssh_paths[0],
        ssh_public_key_path_to_save=ssh_paths[1],
    )
    p2 = ProfileData(
        federee=Federee.ECMWF,
        tenant_name="B",
        ssh_private_key_path_to_save=ssh_paths[0],
        ssh_public_key_path_to_save=ssh_paths[1],
    )

    store.save(p1)
    store.save(p2)

    profiles = store.list_profiles()
    assert set(profiles) == {"EUMETSAT-A", "ECMWF-B"}


# ---------------------------------------------------------------------------
# exists
# ---------------------------------------------------------------------------

def test_exists(profile_file, ssh_paths):
    store = ProfileStore(path=profile_file)

    data = ProfileData(
        federee=Federee.EUMETSAT,
        tenant_name="TeamX",
        ssh_private_key_path_to_save=ssh_paths[0],
        ssh_public_key_path_to_save=ssh_paths[1],
    )

    assert not store.exists("EUMETSAT-TeamX")
    store.save(data)
    assert store.exists("EUMETSAT-TeamX")


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_profiledata_validation_missing_fields():
    with pytest.raises(Exception):
        ProfileData(
            federee=Federee.EUMETSAT,
            tenant_name="TeamA",
            # missing ssh keys → must fail
        )