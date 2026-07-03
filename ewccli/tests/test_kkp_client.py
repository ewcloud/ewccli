"""Tests for the KKP API client (OIDC kubeconfig endpoint)."""

import pytest
from unittest.mock import patch, MagicMock

from ewccli.backends.kkp.kkp_client import KKPClient, KKPError


@pytest.fixture
def client():
    return KKPClient(
        api_url="https://k8s-val.example.com",
        token="oidc-token-123",
    )


@patch("ewccli.backends.kkp.kkp_client.requests.get")
def test_get_oidc_kubeconfig_success_returns_body(mock_get, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "apiVersion: v1\nkind: Config"
    mock_get.return_value = mock_response

    result = client.get_oidc_kubeconfig(
        project_id="a0f3891de6",
        cluster_id="abv9l8vmfm",
    )

    assert result == "apiVersion: v1\nkind: Config"

    call_args = mock_get.call_args
    assert call_args[0][0] == (
        "https://k8s-val.example.com/api/v2/projects/a0f3891de6"
        "/clusters/abv9l8vmfm/oidckubeconfig"
    )
    assert call_args[1]["headers"]["Authorization"] == "Bearer oidc-token-123"
    assert call_args[1]["timeout"] == 30


@patch("ewccli.backends.kkp.kkp_client.requests.get")
def test_get_oidc_kubeconfig_401_raises_kkp_error(mock_get, client):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "unauthorized"
    mock_get.return_value = mock_response

    with pytest.raises(KKPError) as exc_info:
        client.get_oidc_kubeconfig("proj", "cluster")

    assert exc_info.value.status_code == 401
    assert "401" in str(exc_info.value)
    assert exc_info.value.body == "unauthorized"


@patch("ewccli.backends.kkp.kkp_client.requests.get")
def test_get_oidc_kubeconfig_404_raises_kkp_error(mock_get, client):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "not found"
    mock_get.return_value = mock_response

    with pytest.raises(KKPError) as exc_info:
        client.get_oidc_kubeconfig("missing-proj", "missing-cluster")

    assert exc_info.value.status_code == 404


@patch("ewccli.backends.kkp.kkp_client.requests.get")
def test_get_oidc_kubeconfig_request_exception_raises_kkp_error(mock_get, client):
    import requests as req

    mock_get.side_effect = req.RequestException("connection refused")

    with pytest.raises(KKPError, match="request failed"):
        client.get_oidc_kubeconfig("proj", "cluster")


def test_client_strips_trailing_slash():
    c = KKPClient(api_url="https://example.com/", token="t")
    assert c._url == "https://example.com"
