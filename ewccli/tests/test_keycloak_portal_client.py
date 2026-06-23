"""Tests for the portal API client."""
import pytest
from unittest.mock import patch, MagicMock

from ewccli.backends.keycloak.portal_client import PortalClient, PortalCredentials


@pytest.fixture
def portal_client():
    return PortalClient(
        portal_api_url="https://europeanweather.cloud",
    )


def test_credentials_endpoint(portal_client):
    assert portal_client.credentials_endpoint == (
        "https://europeanweather.cloud/api/v1/credentials/openstack"
    )


def test_credentials_endpoint_strips_trailing_slash():
    client = PortalClient(portal_api_url="https://example.com/")
    assert client.credentials_endpoint == "https://example.com/api/v1/credentials/openstack"


@patch("ewccli.backends.keycloak.portal_client.requests.post")
def test_fetch_openstack_credentials(mock_post, portal_client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "application_credential_id": "app-id-123",
        "application_credential_secret": "app-secret-456",
        "auth_url": "https://keystone.api.r1.cloud.eumetsat.int",
        "federee": "EUMETSAT",
        "region": "ECIS-R1",
        "tenant_name": "my-tenant",
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    creds = portal_client.fetch_openstack_credentials(
        access_token="oidc-token-789",
    )

    assert isinstance(creds, PortalCredentials)
    assert creds.application_credential_id == "app-id-123"
    assert creds.application_credential_secret == "app-secret-456"
    assert creds.auth_url == "https://keystone.api.r1.cloud.eumetsat.int"
    assert creds.federee == "EUMETSAT"
    assert creds.region == "ECIS-R1"
    assert creds.tenant_name == "my-tenant"

    call_args = mock_post.call_args
    assert "Bearer oidc-token-789" in call_args[1]["headers"]["Authorization"]
    # No body when federee/region not provided
    assert call_args[1]["json"] is None


@patch("ewccli.backends.keycloak.portal_client.requests.post")
def test_fetch_openstack_credentials_with_federee_region(mock_post, portal_client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "application_credential_id": "id",
        "application_credential_secret": "secret",
        "auth_url": "https://keystone.example.com",
        "federee": "ECMWF",
        "region": "CC1",
        "tenant_name": "tenant",
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    portal_client.fetch_openstack_credentials(
        access_token="token",
        federee="ECMWF",
        region="CC1",
    )

    call_args = mock_post.call_args
    assert call_args[1]["json"]["federee"] == "ECMWF"
    assert call_args[1]["json"]["region"] == "CC1"


@patch("ewccli.backends.keycloak.portal_client.requests.post")
def test_fetch_openstack_credentials_http_error(mock_post, portal_client):
    import requests as req

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("403 Forbidden")
    mock_post.return_value = mock_response

    with pytest.raises(req.exceptions.HTTPError):
        portal_client.fetch_openstack_credentials(access_token="bad-token")


@patch("ewccli.backends.keycloak.portal_client.requests.post")
def test_fetch_openstack_credentials_missing_fields(mock_post, portal_client):
    """Portal returns only required fields, optionals are None."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "application_credential_id": "id",
        "application_credential_secret": "secret",
        "auth_url": "https://keystone.example.com",
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    creds = portal_client.fetch_openstack_credentials(access_token="token")

    assert creds.application_credential_id == "id"
    assert creds.application_credential_secret == "secret"
    assert creds.auth_url == "https://keystone.example.com"
    assert creds.federee is None
    assert creds.region is None
    assert creds.tenant_name is None
