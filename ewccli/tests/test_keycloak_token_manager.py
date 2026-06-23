"""Tests for the token manager."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from click import ClickException

from ewccli.backends.keycloak.token_manager import (
    _parse_iso_timestamp,
    _is_expired,
    _compute_expires_at,
    get_valid_access_token,
    _update_profile_tokens,
)


def test_parse_iso_timestamp_with_z():
    ts = _parse_iso_timestamp("2026-06-23T12:00:00Z")
    assert ts is not None
    assert ts.year == 2026
    assert ts.month == 6
    assert ts.day == 23


def test_parse_iso_timestamp_with_offset():
    ts = _parse_iso_timestamp("2026-06-23T12:00:00+00:00")
    assert ts is not None
    assert ts.tzinfo is not None


def test_parse_iso_timestamp_none():
    assert _parse_iso_timestamp(None) is None
    assert _parse_iso_timestamp("") is None


def test_parse_iso_timestamp_invalid():
    assert _parse_iso_timestamp("not-a-date") is None


def test_is_expired_with_past_time():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert _is_expired(past) is True


def test_is_expired_with_future_time():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _is_expired(future) is False


def test_is_expired_with_soon_future():
    """Token expiring within the skew window should be considered expired."""
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    assert _is_expired(soon, skew_seconds=60) is True


def test_is_expired_none():
    assert _is_expired(None) is True


def test_compute_expires_at():
    expires_at = _compute_expires_at(300)
    parsed = _parse_iso_timestamp(expires_at)
    assert parsed is not None
    # Should be about 5 minutes in the future
    now = datetime.now(timezone.utc)
    delta = parsed - now
    assert 290 <= delta.total_seconds() <= 305


def test_get_valid_access_token_returns_valid_token():
    """If the access token is not expired, return it without refreshing."""
    profile = {
        "profile": "test",
        "keycloak_access_token": "valid-token",
        "keycloak_token_expires_at": (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(),
        "keycloak_refresh_token": "refresh-token",
    }
    result = get_valid_access_token(profile)
    assert result == "valid-token"


@patch("ewccli.backends.keycloak.token_manager.OIDCClient")
def test_get_valid_access_token_refreshes_expired_token(mock_oidc_cls):
    mock_oidc = MagicMock()
    mock_oidc.refresh_tokens.return_value = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "id_token": "new-id",
        "expires_in": 300,
    }
    mock_oidc_cls.return_value = mock_oidc

    profile = {
        "profile": "test",
        "keycloak_access_token": "old-access",
        "keycloak_token_expires_at": (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat(),
        "keycloak_refresh_token": "old-refresh",
    }

    with patch(
        "ewccli.backends.keycloak.token_manager._update_profile_tokens"
    ) as mock_update:
        result = get_valid_access_token(profile)
        assert result == "new-access"
        mock_oidc.refresh_tokens.assert_called_once_with(refresh_token="old-refresh")
        mock_update.assert_called_once()


def test_get_valid_access_token_no_refresh_token_raises():
    profile = {
        "profile": "test",
        "keycloak_access_token": "expired",
        "keycloak_token_expires_at": (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat(),
        "keycloak_refresh_token": None,
    }
    with pytest.raises(ClickException, match="session has expired"):
        get_valid_access_token(profile)


@patch("ewccli.backends.keycloak.token_manager.OIDCClient")
def test_get_valid_access_token_refresh_failure_raises(mock_oidc_cls):
    mock_oidc = MagicMock()
    mock_oidc.refresh_tokens.side_effect = Exception("invalid_grant")
    mock_oidc_cls.return_value = mock_oidc

    profile = {
        "profile": "test",
        "keycloak_access_token": "expired",
        "keycloak_token_expires_at": (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat(),
        "keycloak_refresh_token": "old-refresh",
    }
    with pytest.raises(ClickException, match="could not be refreshed"):
        get_valid_access_token(profile)


def test_update_profile_tokens(tmp_path):
    from configparser import ConfigParser

    profiles_file = tmp_path / "profiles"
    cfg = ConfigParser()
    cfg["test"] = {
        "federee": "EUMETSAT",
        "keycloak_access_token": "old",
    }
    with open(profiles_file, "w") as f:
        cfg.write(f)

    _update_profile_tokens(
        profiles_file_path=profiles_file,
        profile_name="test",
        access_token="new-token",
        refresh_token="new-refresh",
        expires_at="2026-06-23T13:00:00+00:00",
        id_token="new-id",
    )

    cfg2 = ConfigParser()
    cfg2.read(profiles_file)
    assert cfg2["test"]["keycloak_access_token"] == "new-token"
    assert cfg2["test"]["keycloak_refresh_token"] == "new-refresh"
    assert cfg2["test"]["keycloak_id_token"] == "new-id"
    assert cfg2["test"]["keycloak_token_expires_at"] == "2026-06-23T13:00:00+00:00"
    # Existing keys should be preserved
    assert cfg2["test"]["federee"] == "EUMETSAT"
