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
    config.EWC_CLI_OIDC_CALLBACK_TIMEOUT = 10
    config.EWC_CLI_OIDC_CALLBACK_PORT = 0
    return config


@patch("ewccli.backends.keycloak.keycloak_backend.webbrowser")
@patch("ewccli.backends.keycloak.keycloak_backend.OIDCClient")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_success(
    mock_cb_server_cls,
    mock_oidc_cls,
    mock_webbrowser,
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

    result = keycloak_login(
        config=mock_config,
        open_browser=True,
        federee="EUMETSAT",
    )

    assert isinstance(result, KeycloakLoginResult)
    # Only the access token is returned (ephemeral, not stored)
    assert result.access_token == "access123"

    # Browser was opened via webbrowser.open
    mock_webbrowser.open.assert_called_once()

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


@patch("ewccli.backends.keycloak.keycloak_backend.OIDCClient")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_token_exchange_failure(
    mock_cb_server_cls,
    mock_oidc_cls,
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


@patch("ewccli.backends.keycloak.keycloak_backend.webbrowser")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_keyboard_interrupt(
    mock_cb_server_cls,
    mock_webbrowser,
    mock_config,
):
    """Ctrl+C during callback wait should stop the server and raise ClickException."""
    mock_server = MagicMock()
    mock_server.port = 12345
    mock_server.redirect_uri = "http://127.0.0.1:12345/callback"
    mock_server.wait_for_callback.side_effect = KeyboardInterrupt()
    mock_server.error = None
    mock_cb_server_cls.return_value = mock_server

    with pytest.raises(ClickException, match="Authentication cancelled by user"):
        keycloak_login(
            config=mock_config,
            open_browser=False,
        )

    # Server must be stopped even on KeyboardInterrupt
    mock_server.stop.assert_called_once()
