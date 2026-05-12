#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Profile."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict

from configparser import ConfigParser, SectionProxy
from pydantic import BaseModel, Field, ValidationError

import rich_click as click

from ewccli.configuration import config as ewc_hub_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Profile Model
# ---------------------------------------------------------------------------


class ProfileData(BaseModel):  # type: ignore[misc]
    """
    Structured profile data validated by Pydantic.
    """

    federee: str
    region: str
    tenant_name: str
    ssh_private_key_path: str = Field(..., alias="ssh_private_key_path_to_save")
    ssh_public_key_path: str = Field(..., alias="ssh_public_key_path_to_save")

    profile: Optional[str] = None
    token: Optional[str] = None
    application_credential_id: Optional[str] = None
    application_credential_secret: Optional[str] = None

    class Config:
        validate_by_name = True

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_section(cls, name: str, section: SectionProxy) -> "ProfileData":
        """
        Build a ProfileData instance from a ConfigParser section.
        """
        try:
            return cls(
                profile=name,
                federee=section.get("federee"),
                tenant_name=section.get("tenant_name"),
                ssh_public_key_path_to_save=section.get("ssh_public_key_path"),
                ssh_private_key_path_to_save=section.get("ssh_private_key_path"),
                region=section.get("region"),
                token=section.get("token"),
                application_credential_id=section.get("application_credential_id"),
                application_credential_secret=section.get(
                    "application_credential_secret"
                ),
            )
        except ValidationError as exc:
            raise click.ClickException(f"Invalid profile '{name}': {exc}") from exc

    def to_section(self) -> Dict[str, str]:
        """
        Convert this profile into a dict suitable for ConfigParser.
        """
        data = {
            "federee": self.federee,
            "region": self.region,
            "tenant_name": self.tenant_name,
            "ssh_public_key_path": self.ssh_public_key_path,
            "ssh_private_key_path": self.ssh_private_key_path,
        }

        if self.token:
            data["token"] = self.token
        if self.application_credential_id:
            data["application_credential_id"] = self.application_credential_id
        if self.application_credential_secret:
            data["application_credential_secret"] = self.application_credential_secret

        return data


# ---------------------------------------------------------------------------
# Profile Store
# ---------------------------------------------------------------------------


class ProfileStore:
    """
    Manage reading/writing EWC CLI profiles from the profiles file.
    """

    def __init__(self, path: Path = ewc_hub_config.EWC_CLI_PROFILES_PATH):
        self.path = path
        self.cfg = self._load_or_init()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_init(self) -> ConfigParser:
        """
        Load the profiles file if it exists, otherwise return an empty ConfigParser.
        """
        cfg = ConfigParser()
        if self.path.exists():
            cfg.read(self.path)
        return cfg

    def _save(self) -> None:
        """
        Persist the profiles file to disk.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            self.cfg.write(f)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def list_profiles(self) -> list[str]:
        """Return all profile names."""
        return self.cfg.sections()

    def exists(self, name: str) -> bool:
        """Return True if a profile exists."""
        return name in self.cfg.sections()

    def resolve_name(
        self,
        profile: Optional[str] = None,
        federee: Optional[str] = None,
        tenant_name: Optional[str] = None,
        region: Optional[str] = None,
    ) -> str:
        """
        Resolve the profile name from explicit input or federee+tenant.
        """
        if profile:
            return profile

        # Validate required components
        if not federee or not region or not tenant_name:
            click.secho(
                "❌ Either 'profile' must be provided or all of 'federee', 'region', and 'tenant_name'.",
                fg="red",
                bold=True,
            )
            raise click.Abort()

        # Auto-generate profile name
        return f"{federee.lower()}-{region.lower()}-{tenant_name.lower()}"

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, name: str) -> ProfileData:
        """
        Load a profile by name and return a validated ProfileData instance.
        """
        if name not in self.cfg:
            self._error_missing_profile(name)

        section = self.cfg[name]
        return ProfileData.from_section(name, section)

    def _error_missing_profile(self, name: str) -> None:
        click.secho(f"❌ Profile '{name}' not found.", fg="red", bold=True)
        click.secho(f"Searched in: {self.path}", fg="cyan")

        profiles = self.list_profiles()
        if profiles:
            click.secho("ℹ️ Available profiles:", fg="yellow")
            for p in profiles:
                click.secho(f"  • {p}", fg="green")

        raise click.Abort()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, data: ProfileData) -> None:
        """
        Save a validated profile. Fails if the profile already exists.
        """
        name = data.profile or f"{data.federee}-{data.region}-{data.tenant_name}"
        print(name)
        if self.exists(name):
            click.secho(
                f"❌ Profile '{name}' already exists in {self.path}",
                fg="red",
                bold=True,
            )
            click.secho(
                "Use a different profile name or delete the existing profile first.",
                fg="yellow",
            )
            raise click.Abort()
        self.cfg[name] = data.to_section()
        self._save()

    # ------------------------------------------------------------------
    # Save default profile
    # ------------------------------------------------------------------

    def save_default(self, data: ProfileData) -> None:
        """
        Save the default login profile only if it does not exist.
        """
        default_name = ewc_hub_config.EWC_CLI_DEFAULT_PROFILE_NAME

        self.cfg[default_name] = data.to_section()
        self._save()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, name: str) -> None:  # noqa: CCR001
        """
        Delete a profile from the profiles file.

        Parameters
        ----------
        name : str
            Name of the profile to delete.

        Raises
        ------
        click.Abort
            If the profile does not exist or the profiles file is missing/empty.
        """
        # Case 1: file missing or empty
        if not self.path.exists() or not self.cfg.sections():
            click.secho("❌ No profiles found.", fg="red", bold=True)
            click.secho(f"Searched in: {self.path}", fg="cyan")
            click.secho(
                "Please run 'ewc login' first to create a profile.",
                fg="yellow",
            )
            raise click.Abort()

        # Case 2: profile not found
        if name not in self.list_profiles():
            click.secho(f"❌ Profile '{name}' not found.", fg="red", bold=True)
            click.secho(f"Searched in: {self.path}", fg="cyan")

            profiles = self.list_profiles()
            if profiles:
                click.secho("ℹ️ Available profiles:", fg="yellow")
                for p in profiles:
                    click.secho(f"  • {p}", fg="green")

            raise click.Abort()

        # Delete the profile
        self.cfg.remove_section(name)
        self._save()

        click.secho(
            f"🗑️ Profile '{name}' deleted successfully.",
            fg="green",
            bold=True,
        )
