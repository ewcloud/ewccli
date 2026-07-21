#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""KKP API client — fetches OIDC kubeconfigs from Kubermatic KKP.

Uses the kubermatic-audience token obtained via kubelogin to call the
``/api/v2/projects/{pid}/clusters/{cid}/oidckubeconfig`` endpoint.
"""

from typing import Optional

import requests

from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


class KKPError(Exception):
    """Raised when a KKP API call fails.

    Carries the HTTP status code (when available) and the response body
    so callers can produce clear error messages.
    """

    def __init__(self, message: str, status_code: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class KKPClient:
    """Client for the KKP API (OIDC kubeconfig endpoint only)."""

    def __init__(self, api_url: str, token: str):
        self._url = api_url.rstrip("/")
        self._token = token

    def get_oidc_kubeconfig(self, project_id: str, cluster_id: str) -> str:
        """Fetch the raw OIDC kubeconfig YAML for a user cluster.

        GET /api/v2/projects/{project_id}/clusters/{cluster_id}/oidckubeconfig

        Returns:
            The kubeconfig YAML as a string.

        Raises:
            KKPError: On HTTP errors or request failures.
        """
        endpoint = (
            f"{self._url}/api/v2/projects/{project_id}"
            f"/clusters/{cluster_id}/oidckubeconfig"
        )
        headers = {"Authorization": f"Bearer {self._token}"}

        _LOGGER.debug("KKP API GET %s", endpoint)

        try:
            resp = requests.get(endpoint, headers=headers, timeout=30)
        except requests.RequestException as e:
            raise KKPError(f"KKP API request failed: {e}") from e

        if resp.status_code != 200:
            raise KKPError(
                f"KKP API returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text,
            )

        return resp.text
