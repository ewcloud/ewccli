"""OIDC client for Keycloak authorization code + PKCE flow."""

from typing import Optional
from urllib.parse import urlencode

import requests

from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


class OIDCClient:
    """Handles OIDC authorization URL construction and token exchange."""

    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        client_id: str,
        scope: str = "openid profile email",
    ):
        self._keycloak_url = keycloak_url.rstrip("/")
        self._realm = realm
        self._client_id = client_id
        self._scope = scope

    @property
    def authorization_endpoint(self) -> str:
        return (
            f"{self._keycloak_url}/realms/{self._realm}"
            "/protocol/openid-connect/auth"
        )

    @property
    def token_endpoint(self) -> str:
        return (
            f"{self._keycloak_url}/realms/{self._realm}"
            "/protocol/openid-connect/token"
        )

    def build_authorization_url(
        self,
        redirect_uri: str,
        code_challenge: str,
        state: str,
    ) -> str:
        """Build the OIDC authorization URL with PKCE."""
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._scope,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> dict:
        """Exchange the authorization code for access/refresh tokens.

        Returns the token response dict with keys:
        access_token, refresh_token, id_token, expires_in, token_type.
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "code_verifier": code_verifier,
        }
        _LOGGER.debug("Exchanging authorization code for tokens")
        response = requests.post(self.token_endpoint, data=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def refresh_tokens(self, refresh_token: str) -> dict:
        """Use a refresh token to obtain new tokens.

        With refresh token rotation enabled in Keycloak, this returns a
        NEW refresh_token and invalidates the old one.

        Returns the token response dict.
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id,
        }
        _LOGGER.debug("Refreshing OIDC tokens")
        response = requests.post(self.token_endpoint, data=data, timeout=30)
        response.raise_for_status()
        return response.json()
