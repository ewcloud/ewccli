"""Tests for the OIDC client."""
import pytest
from unittest.mock import patch, MagicMock

from ewccli.backends.keycloak.oidc_client import OIDCClient


@pytest.fixture
def oidc_client():
    return OIDCClient(
        keycloak_url="https://auth.example.com",
        realm="ewc",
        client_id="ewccli",
        scope="openid profile",
    )


def test_build_authorization_url(oidc_client):
    url = oidc_client.build_authorization_url(
        redirect_uri="http://127.0.0.1:12345/callback",
        code_challenge="mychallenge",
        state="mystate",
    )
    assert "https://auth.example.com/realms/ewc/protocol/openid-connect/auth" in url
    assert "client_id=ewccli" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "code_challenge=mychallenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=mystate" in url
    assert "scope=openid" in url


def test_authorization_endpoint(oidc_client):
    assert oidc_client.authorization_endpoint == (
        "https://auth.example.com/realms/ewc/protocol/openid-connect/auth"
    )


def test_token_endpoint(oidc_client):
    assert oidc_client.token_endpoint == (
        "https://auth.example.com/realms/ewc/protocol/openid-connect/token"
    )


@patch("ewccli.backends.keycloak.oidc_client.requests.post")
def test_exchange_code_for_tokens(mock_post, oidc_client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "access123",
        "refresh_token": "refresh456",
        "id_token": "id789",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    tokens = oidc_client.exchange_code_for_tokens(
        code="mycode",
        code_verifier="myverifier",
        redirect_uri="http://127.0.0.1:12345/callback",
    )

    assert tokens["access_token"] == "access123"
    assert tokens["refresh_token"] == "refresh456"
    assert tokens["id_token"] == "id789"
    assert tokens["expires_in"] == 3600

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "token" in call_args[0][0]
    assert call_args[1]["data"]["grant_type"] == "authorization_code"
    assert call_args[1]["data"]["code"] == "mycode"
    assert call_args[1]["data"]["code_verifier"] == "myverifier"
    assert call_args[1]["data"]["client_id"] == "ewccli"


@patch("ewccli.backends.keycloak.oidc_client.requests.post")
def test_refresh_tokens(mock_post, oidc_client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_in": 300,
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    tokens = oidc_client.refresh_tokens(refresh_token="old_refresh")

    assert tokens["access_token"] == "new_access"
    assert tokens["refresh_token"] == "new_refresh"

    call_args = mock_post.call_args
    assert call_args[1]["data"]["grant_type"] == "refresh_token"
    assert call_args[1]["data"]["refresh_token"] == "old_refresh"
    assert call_args[1]["data"]["client_id"] == "ewccli"


@patch("ewccli.backends.keycloak.oidc_client.requests.post")
def test_exchange_code_raises_on_http_error(mock_post, oidc_client):
    import requests as req

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("400")
    mock_post.return_value = mock_response

    with pytest.raises(req.exceptions.HTTPError):
        oidc_client.exchange_code_for_tokens(
            code="badcode",
            code_verifier="verifier",
            redirect_uri="http://127.0.0.1:12345/callback",
        )
