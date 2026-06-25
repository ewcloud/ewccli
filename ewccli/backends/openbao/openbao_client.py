#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""OpenBao client — OIDC login and KV2 secret reads."""

from typing import Optional

import requests

from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


class OpenBaoError(Exception):
    """Raised when an OpenBao API call fails.

    Carries the HTTP status code (when available) and the response body
    so callers can produce clear error messages.
    """

    def __init__(self, message: str, status_code: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class OpenBaoClient:
    """Client for OpenBao OIDC auth and KV2 secret reads.

    The Keycloak access token is exchanged for an ephemeral OpenBao client
    token via the OIDC auth method. That client token is then used to read
    KV2 secrets. Neither token is persisted by this client.
    """

    def __init__(
        self,
        url: str,
        namespace: str,
        role: str,
        kv_mount: str,
        access_token: str,
    ):
        self._url = url.rstrip("/")
        self._namespace = namespace
        self._role = role
        self._kv_mount = kv_mount
        self._access_token = access_token
        self._client_token: Optional[str] = None

    def _namespace_headers(self) -> dict:
        headers = {}
        if self._namespace:
            headers["X-Vault-Namespace"] = self._namespace
        return headers

    def login(self) -> str:
        """Authenticate to OpenBao using the OIDC (JWT) auth method.

        POSTs the Keycloak access token to
        ``/v1/auth/oidc/login/{role}`` and returns ``auth.client_token``.

        Returns:
            The OpenBao client token.

        Raises:
            OpenBaoError: On HTTP errors or malformed responses.
        """
        endpoint = f"{self._url}/v1/auth/oidc/login/{self._role}"
        headers = self._namespace_headers()
        headers["Content-Type"] = "application/json"
        body = {"jwt": self._access_token}

        _LOGGER.debug("OpenBao OIDC login to %s", endpoint)

        try:
            response = requests.post(endpoint, headers=headers, json=body, timeout=30)
        except requests.RequestException as e:
            raise OpenBaoError(f"OpenBao login request failed: {e}") from e

        if response.status_code != 200:
            raise OpenBaoError(
                f"OpenBao OIDC login failed with status {response.status_code}",
                status_code=response.status_code,
                body=response.text,
            )

        try:
            data = response.json()
        except ValueError as e:
            raise OpenBaoError(f"OpenBao login returned invalid JSON: {e}") from e

        client_token = (data.get("auth") or {}).get("client_token")
        if not client_token:
            raise OpenBaoError("OpenBao login response missing auth.client_token")

        self._client_token = client_token
        return client_token

    def read_secret(self, path: str) -> dict:
        """Read a KV2 secret at ``secret/data/{path}``.

        Requires :meth:`login` to have been called (or a client token
        to have been obtained otherwise).

        Returns:
            The inner ``data.data`` dict of the KV2 secret.

        Raises:
            OpenBaoError: On HTTP errors or malformed responses.
        """
        if not self._client_token:
            raise OpenBaoError(
                "No OpenBao client token available. Call login() first."
            )

        endpoint = f"{self._url}/v1/{self._kv_mount}/data/{path}"
        headers = self._namespace_headers()
        headers["Authorization"] = f"Bearer {self._client_token}"

        _LOGGER.debug("OpenBao KV2 read from %s", endpoint)

        try:
            response = requests.get(endpoint, headers=headers, timeout=30)
        except requests.RequestException as e:
            raise OpenBaoError(f"OpenBao secret read request failed: {e}") from e

        if response.status_code not in (200, 204):
            raise OpenBaoError(
                f"OpenBao secret read failed with status {response.status_code}",
                status_code=response.status_code,
                body=response.text,
            )

        try:
            data = response.json()
        except ValueError as e:
            raise OpenBaoError(
                f"OpenBao secret read returned invalid JSON: {e}"
            ) from e

        inner = (data.get("data") or {}).get("data")
        if inner is None:
            raise OpenBaoError("OpenBao secret response missing data.data")

        return inner
