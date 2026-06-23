"""Tests for the Keycloak login orchestrator."""
import pytest
from unittest.mock import patch, MagicMock
from click import ClickException

from ewccli.backends.keycloak.keycloak_backend import keycloak_login, KeycloakLoginResult


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.EWC_CLI_KEYCLOAK_URL = "https://auth.example.com"
    config.EWC_CLI_KEYCLOAK_REALM = "ewc"
    config.EWC_CLI_KEYCLOAK_CLIENT_ID = "ewccli"
    config.EWC_CLI_KEYCLOAK_SCOPE = "openid profile"
    config.EWC_CLI_PORTAL_API_URL = "https://portal.example.com"
    config.EWC_CLI_OIDC_CALLBACK_TIMEOUT = 10
    return config


@pytest.fixture
def mock_config_no_portal():
    config = MagicMock()
    config.EWC_CLI_KEYCLOAK_URL = "https://auth.example.com"
    config.EWC_CLI_KEYCLOAK_REALM = "ewc"
    config.EWC_CLI_KEYCLOAK_CLIENT_ID = "ewccli"
    config.EWC_CLI_KEYCLOAK_SCOPE = "openid profile"
    config.EWC_CLI_PORTAL_API_URL = ""
    config.EWC_CLI_OIDC_CALLBACK_TIMEOUT = 10
    return config


@patch("ewccli.backends.keycloak.keycloak_backend.subprocess")
@patch("ewccli.backends.keycloak.keycloak_backend.webbrowser")
@patch("ewccli.backends.keycloak.keycloak_backend.PortalClient")
@patch("ewccli.backends.keycloak.keycloak_backend.OIDCClient")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_success(
    mock_cb_server_cls,
    mock_oidc_cls,
    mock_portal_cls,
    mock_webbrowser,
    mock_subprocess,
    mock_config,
):
    # Callback server
    mock_server = MagicMock()
    mock_server.port = 12345
    mock_server.redirect_uri = "http://127.0.0.1:12345/callback"
    mock_server.wait_for_callback.return_value = ("mycode", "mystate")
    mock_server.error = None
    mock_cb_server_cls.return_value = mock_server

    # OIDC client
    mock_oidc = MagicMock()
    mock_oidc.build_authorization_url.return_value = "https://auth.example.com/auth?..."
    mock_oidc.exchange_code_for_tokens.return_value = {
        "access_token": "access123",
        "refresh_token": "refresh456",
        "id_token": "id789",
        "expires_in": 3600,
    }
    mock_oidc_cls.return_value = mock_oidc

    # Portal client
    mock_portal = MagicMock()
    mock_creds = MagicMock()
    mock_creds.application_credential_id = "app-id"
    mock_creds.application_credential_secret = "app-secret"
    mock_creds.auth_url = "https://keystone.example.com"
    mock_creds.federee = "EUMETSAT"
    mock_creds.region = "ECIS-R1"
    mock_creds.tenant_name = "tenant"
    mock_portal.fetch_openstack_credentials.return_value = mock_creds
    mock_portal_cls.return_value = mock_portal

    result = keycloak_login(
        config=mock_config,
        open_browser=True,
        federee="EUMETSAT",
        region="ECIS-R1",
    )

    assert isinstance(result, KeycloakLoginResult)
    assert result.application_credential_id == "app-id"
    assert result.application_credential_secret == "app-secret"
    assert result.auth_url == "https://keystone.example.com"
    assert result.access_token == "access123"
    assert result.refresh_token == "refresh456"
    assert result.federee == "EUMETSAT"
    assert result.region == "ECIS-R1"

    # Browser was opened (via subprocess.Popen)
    mock_subprocess.Popen.assert_called_once()
    # webbrowser.open should not be called (subprocess takes priority)
    mock_webbrowser.open.assert_not_called()

    # Callback server was started and stopped
    mock_server.start.assert_called_once()
    mock_server.stop.assert_called_once()


@patch("ewccli.backends.keycloak.keycloak_backend.webbrowser")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_timeout(
    mock_cb_server_cls,
    mock_webbrowser,
    mock_config,
):
    mock_server = MagicMock()
    mock_server.port = 12345
    mock_server.redirect_uri = "http://127.0.0.1:12345/callback"
    mock_server.wait_for_callback.return_value = None  # timeout
    mock_server.error = None
    mock_cb_server_cls.return_value = mock_server

    with pytest.raises(ClickException, match="timed out"):
        keycloak_login(
            config=mock_config,
            open_browser=False,
        )


@patch("ewccli.backends.keycloak.keycloak_backend.webbrowser")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_state_mismatch(
    mock_cb_server_cls,
    mock_webbrowser,
    mock_config,
):
    mock_server = MagicMock()
    mock_server.port = 12345
    mock_server.redirect_uri = "http://127.0.0.1:12345/callback"
    mock_server.wait_for_callback.return_value = None
    mock_server.error = "State mismatch"
    mock_cb_server_cls.return_value = mock_server

    with pytest.raises(ClickException, match="State mismatch"):
        keycloak_login(
            config=mock_config,
            open_browser=False,
        )


@patch("ewccli.backends.keycloak.keycloak_backend.PortalClient")
@patch("ewccli.backends.keycloak.keycloak_backend.OIDCClient")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_token_exchange_failure(
    mock_cb_server_cls,
    mock_oidc_cls,
    mock_portal_cls,
    mock_config,
):
    mock_server = MagicMock()
    mock_server.port = 12345
    mock_server.redirect_uri = "http://127.0.0.1:12345/callback"
    mock_server.wait_for_callback.return_value = ("code", "state")
    mock_server.error = None
    mock_cb_server_cls.return_value = mock_server

    mock_oidc = MagicMock()
    mock_oidc.exchange_code_for_tokens.side_effect = Exception("token endpoint down")
    mock_oidc_cls.return_value = mock_oidc

    with pytest.raises(ClickException, match="Failed to exchange"):
        keycloak_login(config=mock_config, open_browser=False)


@patch("ewccli.backends.keycloak.keycloak_backend.PortalClient")
@patch("ewccli.backends.keycloak.keycloak_backend.OIDCClient")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_portal_failure(
    mock_cb_server_cls,
    mock_oidc_cls,
    mock_portal_cls,
    mock_config,
):
    mock_server = MagicMock()
    mock_server.port = 12345
    mock_server.redirect_uri = "http://127.0.0.1:12345/callback"
    mock_server.wait_for_callback.return_value = ("code", "state")
    mock_server.error = None
    mock_cb_server_cls.return_value = mock_server

    mock_oidc = MagicMock()
    mock_oidc.exchange_code_for_tokens.return_value = {
        "access_token": "token",
        "refresh_token": "refresh",
        "expires_in": 300,
    }
    mock_oidc_cls.return_value = mock_oidc

    mock_portal = MagicMock()
    mock_portal.fetch_openstack_credentials.side_effect = Exception("403 Forbidden")
    mock_portal_cls.return_value = mock_portal

    with pytest.raises(ClickException, match="Failed to fetch OpenStack credentials"):
        keycloak_login(config=mock_config, open_browser=False)


@patch("ewccli.backends.keycloak.keycloak_backend.PortalClient")
@patch("ewccli.backends.keycloak.keycloak_backend.OIDCClient")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_no_portal_returns_empty_creds(
    mock_cb_server_cls,
    mock_oidc_cls,
    mock_portal_cls,
    mock_config_no_portal,
):
    """When portal is not configured, return empty app creds but keep OIDC tokens."""
    mock_server = MagicMock()
    mock_server.port = 12345
    mock_server.redirect_uri = "http://127.0.0.1:12345/callback"
    mock_server.wait_for_callback.return_value = ("code", "state")
    mock_server.error = None
    mock_cb_server_cls.return_value = mock_server

    mock_oidc = MagicMock()
    mock_oidc.exchange_code_for_tokens.return_value = {
        "access_token": "access123",
        "refresh_token": "refresh456",
        "id_token": "id789",
        "expires_in": 300,
    }
    mock_oidc_cls.return_value = mock_oidc

    result = keycloak_login(
        config=mock_config_no_portal,
        open_browser=False,
        federee="EUMETSAT",
        region="ECIS-R1",
    )

    assert isinstance(result, KeycloakLoginResult)
    # App creds are empty — fall through to existing credential path
    assert result.application_credential_id == ""
    assert result.application_credential_secret == ""
    assert result.auth_url == ""
    # OIDC tokens are still stored for refresh
    assert result.access_token == "access123"
    assert result.refresh_token == "refresh456"
    assert result.id_token == "id789"
    # Portal client was never called
    mock_portal_cls.assert_not_called()
