"""Token manager — handles silent OIDC token refresh with rotation."""

from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path
from configparser import ConfigParser
import os

from click import ClickException

from ewccli.backends.keycloak.oidc_client import OIDCClient
from ewccli.configuration import config as ewc_hub_config
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)

# Refresh if the access token expires within this many seconds
_REFRESH_SKEW_SECONDS = 60


def _parse_iso_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string into a timezone-aware datetime."""
    if not ts:
        return None
    try:
        # Handle both with and without 'Z' suffix
        clean = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except (ValueError, TypeError):
        return None


def _is_expired(expires_at: Optional[datetime], skew_seconds: int = _REFRESH_SKEW_SECONDS) -> bool:
    """Check if a token is expired or about to expire (within skew window)."""
    if expires_at is None:
        return True
    now = datetime.now(timezone.utc)
    return now >= (expires_at - timedelta(seconds=skew_seconds))


def _compute_expires_at(expires_in: int) -> str:
    """Compute the absolute expiry timestamp from an expires_in value."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return expiry.isoformat()


def get_valid_access_token(
    profile: dict,
    profiles_file_path: Optional[Path] = None,
) -> str:
    """Return a valid access token, refreshing if necessary.

    This function checks if the stored access token is still valid. If not,
    it attempts a silent refresh using the stored refresh token. On success,
    it updates the profile INI file with the new tokens (rotation). On failure,
    it raises a ClickException telling the user to re-authenticate.

    Args:
        profile: The loaded CLI profile dict (from load_cli_profile()).
        profiles_file_path: Path to the profiles INI file. Defaults to the
            standard EWC_CLI_PROFILES_PATH.

    Returns:
        A valid access token string.

    Raises:
        ClickException: If the refresh token is missing, expired, or invalid.
    """
    if profiles_file_path is None:
        profiles_file_path = ewc_hub_config.EWC_CLI_PROFILES_PATH

    access_token = profile.get("keycloak_access_token")
    expires_at_str = profile.get("keycloak_token_expires_at")
    refresh_token = profile.get("keycloak_refresh_token")

    # If the access token is still valid, return it
    expires_at = _parse_iso_timestamp(expires_at_str)
    if access_token and not _is_expired(expires_at):
        return access_token

    # Token is expired or about to expire — try to refresh
    if not refresh_token:
        raise ClickException(
            "Your EWC session has expired. "
            "Please run: ewc login --keycloak"
        )

    _LOGGER.info("Access token expired, attempting silent refresh...")

    oidc_client = OIDCClient(
        keycloak_url=ewc_hub_config.EWC_CLI_KEYCLOAK_URL,
        realm=ewc_hub_config.EWC_CLI_KEYCLOAK_REALM,
        client_id=ewc_hub_config.EWC_CLI_KEYCLOAK_CLIENT_ID,
        scope=ewc_hub_config.EWC_CLI_KEYCLOAK_SCOPE,
    )

    try:
        new_tokens = oidc_client.refresh_tokens(refresh_token=refresh_token)
    except Exception as e:
        raise ClickException(
            f"Your EWC session has expired and could not be refreshed: {e}. "
            "Please run: ewc login --keycloak"
        )

    new_access_token = new_tokens.get("access_token")
    new_refresh_token = new_tokens.get("refresh_token")
    new_expires_in = new_tokens.get("expires_in", 300)
    new_expires_at = _compute_expires_at(new_expires_in)

    if not new_access_token:
        raise ClickException(
            "Token refresh succeeded but no access_token was returned. "
            "Please run: ewc login --keycloak"
        )

    # Update the profile INI with the rotated tokens
    _update_profile_tokens(
        profiles_file_path=profiles_file_path,
        profile_name=profile.get("profile"),
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_at=new_expires_at,
        id_token=new_tokens.get("id_token"),
    )

    _LOGGER.info("Successfully refreshed OIDC tokens.")

    return new_access_token


def _update_profile_tokens(
    profiles_file_path: Path,
    profile_name: Optional[str],
    access_token: str,
    refresh_token: Optional[str],
    expires_at: str,
    id_token: Optional[str] = None,
) -> None:
    """Update the OIDC token fields in the profile INI file."""
    if not profile_name:
        _LOGGER.warning("No profile name provided, cannot persist refreshed tokens.")
        return

    cfg = ConfigParser()
    cfg.read(profiles_file_path)

    if profile_name not in cfg:
        _LOGGER.warning(f"Profile '{profile_name}' not found, cannot persist refreshed tokens.")
        return

    cfg[profile_name]["keycloak_access_token"] = access_token
    if refresh_token:
        cfg[profile_name]["keycloak_refresh_token"] = refresh_token
    if id_token:
        cfg[profile_name]["keycloak_id_token"] = id_token
    cfg[profile_name]["keycloak_token_expires_at"] = expires_at

    with open(profiles_file_path, "w") as f:
        cfg.write(f)
