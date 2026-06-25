"""Tests for the OpenBao client (OIDC login + KV2 secret reads)."""

import pytest
from unittest.mock import patch, MagicMock

from ewccli.backends.openbao.openbao_client import OpenBaoClient, OpenBaoError


@pytest.fixture
def client():
    return OpenBaoClient(
        url="https://secrets.example.com",
        namespace="openbao-users",
        role="default",
        kv_mount="secret",
        access_token="kc-access-token",
    )


@patch("ewccli.backends.openbao.openbao_client.requests.post")
def test_login_success_returns_client_token(mock_post, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "auth": {"client_token": "bao-token-123"},
    }
    mock_post.return_value = mock_response

    token = client.login()

    assert token == "bao-token-123"
    # Verify the request was made to the OIDC login endpoint
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://secrets.example.com/v1/auth/oidc/login/default"
    assert call_args[1]["headers"]["X-Vault-Namespace"] == "openbao-users"
    assert call_args[1]["json"] == {"jwt": "kc-access-token"}


@patch("ewccli.backends.openbao.openbao_client.requests.post")
def test_login_failure_401_raises_openbao_error(mock_post, client):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "unauthorized"
    mock_post.return_value = mock_response

    with pytest.raises(OpenBaoError) as exc_info:
        client.login()

    assert exc_info.value.status_code == 401
    assert "401" in str(exc_info.value)


@patch("ewccli.backends.openbao.openbao_client.requests.post")
def test_login_missing_client_token_raises(mock_post, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"auth": {}}
    mock_post.return_value = mock_response

    with pytest.raises(OpenBaoError, match="client_token"):
        client.login()


@patch("ewccli.backends.openbao.openbao_client.requests.get")
def test_read_secret_success_returns_data_dict(mock_get, client):
    # First login so the client has a token
    client._client_token = "bao-token-123"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "data": {
                "kubeconfig": "apiVersion: v1",
                "application_credential_id": "app-id",
                "application_credential_secret": "app-secret",
            }
        }
    }
    mock_get.return_value = mock_response

    data = client.read_secret("user-123")

    assert data["application_credential_id"] == "app-id"
    assert data["application_credential_secret"] == "app-secret"
    assert data["kubeconfig"] == "apiVersion: v1"

    call_args = mock_get.call_args
    assert call_args[0][0] == "https://secrets.example.com/v1/secret/data/user-123"
    assert call_args[1]["headers"]["X-Vault-Namespace"] == "openbao-users"
    assert call_args[1]["headers"]["Authorization"] == "Bearer bao-token-123"


@patch("ewccli.backends.openbao.openbao_client.requests.get")
def test_read_secret_failure_403_raises_openbao_error(mock_get, client):
    client._client_token = "bao-token-123"

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "forbidden"
    mock_get.return_value = mock_response

    with pytest.raises(OpenBaoError) as exc_info:
        client.read_secret("user-123")

    assert exc_info.value.status_code == 403


@patch("ewccli.backends.openbao.openbao_client.requests.get")
def test_read_secret_failure_404_raises_openbao_error(mock_get, client):
    client._client_token = "bao-token-123"

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "not found"
    mock_get.return_value = mock_response

    with pytest.raises(OpenBaoError) as exc_info:
        client.read_secret("missing-user")

    assert exc_info.value.status_code == 404


def test_read_secret_without_login_raises(client):
    with pytest.raises(OpenBaoError, match="login"):
        client.read_secret("user-123")


@patch("ewccli.backends.openbao.openbao_client.requests.post")
def test_login_namespace_header_is_sent(mock_post, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"auth": {"client_token": "t"}}
    mock_post.return_value = mock_response

    client.login()

    call_args = mock_post.call_args
    assert call_args[1]["headers"]["X-Vault-Namespace"] == "openbao-users"


def test_openbao_client_without_namespace_omits_header():
    client = OpenBaoClient(
        url="https://secrets.example.com",
        namespace="",
        role="default",
        kv_mount="secret",
        access_token="tok",
    )
    headers = client._namespace_headers()
    assert "X-Vault-Namespace" not in headers
