"""Portal API client — exchanges OIDC tokens for OpenStack application credentials."""

from dataclasses import dataclass
from typing import Optional

import requests

from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


@dataclass
class PortalCredentials:
    """OpenStack application credentials returned by the EWC portal."""

    application_credential_id: str
    application_credential_secret: str
    auth_url: str
    federee: Optional[str] = None
    region: Optional[str] = None
    tenant_name: Optional[str] = None


class PortalClient:
    """Calls the EWC portal API to obtain OpenStack application credentials."""

    def __init__(self, portal_api_url: str):
        self._portal_api_url = portal_api_url.rstrip("/")

    @property
    def credentials_endpoint(self) -> str:
        return f"{self._portal_api_url}/api/v1/credentials/openstack"

    def fetch_openstack_credentials(
        self,
        access_token: str,
        federee: Optional[str] = None,
        region: Optional[str] = None,
    ) -> PortalCredentials:
        """Fetch OpenStack application credentials from the portal API.

        Args:
            access_token: The OIDC access token from Keycloak.
            federee: Optional federee to request credentials for.
            region: Optional region to request credentials for.

        Returns:
            PortalCredentials dataclass with the app cred id/secret and auth_url.

        Raises:
            requests.HTTPError: If the API call fails.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        body: dict = {}
        if federee:
            body["federee"] = federee
        if region:
            body["region"] = region

        _LOGGER.info("Fetching OpenStack credentials from EWC portal")
        response = requests.post(
            self.credentials_endpoint,
            headers=headers,
            json=body if body else None,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        return PortalCredentials(
            application_credential_id=data["application_credential_id"],
            application_credential_secret=data["application_credential_secret"],
            auth_url=data["auth_url"],
            federee=data.get("federee"),
            region=data.get("region"),
            tenant_name=data.get("tenant_name"),
        )
