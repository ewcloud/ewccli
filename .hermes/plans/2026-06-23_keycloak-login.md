# Keycloak OIDC Login for ewccli — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a `ewc login --keycloak` flow that authenticates the user via Keycloak OIDC (authorization code + PKCE), then calls an EWC portal API to obtain OpenStack application credentials, storing them in the existing profile format — fully backward compatible with the current manual-credential login.

**Architecture:**

```
User runs: ewc login --keycloak [--federee X --region Y]

  ┌──────────┐    1. start callback server (127.0.0.1:port)
  │  ewccli  │    2. build auth URL (PKCE code_challenge)
  │          │    3. print URL + open browser
  │          │◄───4. browser redirects with ?code=...&state=...
  │          │    5. exchange code for tokens (code_verifier)
  │          │    6. call portal API with Bearer access_token
  │          │    7. receive app_credential_id/secret/auth_url
  │          │    8. interactive federee/region/SSH (if not from portal)
  │          │    9. save_cli_profile() — same INI format as today
  └──────────┘
```

The downstream OpenStack connection path (`OpenstackBackend.connect()` with `v3applicationcredential`) is unchanged. Keycloak is purely a new *way to obtain* the app creds.

**Tech Stack:** Python stdlib (`http.server`, `secrets`, `hashlib`, `base64`, `urllib.parse`, `webbrowser`, `threading`), `requests` (already a dependency). No new dependencies required.

**Assumed Portal API Contract** (the plan defines this; adjust when the real API is known):

```
POST {EWC_CLI_PORTAL_API_URL}/api/v1/credentials/openstack
Headers: Authorization: Bearer <oidc_access_token>
Body (optional): {"federee": "EUMETSAT", "region": "ECIS-R1"}

Response 200:
{
  "application_credential_id": "...",
  "application_credential_secret": "...",
  "auth_url": "https://keystone.api.r1.cloud.eumetsat.int",
  "federee": "EUMETSAT",
  "region": "ECIS-R1",
  "tenant_name": "user-tenant"
}
```

If `federee`/`region` are omitted from the request, the portal may return the user's default project credentials, or return credentials for all available federees. The CLI handles either case.

**Assumed Keycloak Config** (overridable via env vars):

| Config key | Env var | Default |
|---|---|---|
| `EWC_CLI_KEYCLOAK_URL` | `EWC_CLI_KEYCLOAK_URL` | `https://auth.europeanweather.cloud` |
| `EWC_CLI_KEYCLOAK_REALM` | `EWC_CLI_KEYCLOAK_REALM` | `ewc` |
| `EWC_CLI_KEYCLOAK_CLIENT_ID` | `EWC_CLI_KEYCLOAK_CLIENT_ID` | `ewccli` |
| `EWC_CLI_PORTAL_API_URL` | `EWC_CLI_PORTAL_API_URL` | `https://europeanweather.cloud` |
| `EWC_CLI_KEYCLOAK_SCOPE` | `EWC_CLI_KEYCLOAK_SCOPE` | `openid profile email` |
| `EWC_CLI_OIDC_CALLBACK_TIMEOUT` | `EWC_CLI_OIDC_CALLBACK_TIMEOUT` | `300` (seconds) |

---

## Current State Summary

### Files that matter

| File | Role |
|---|---|
| `ewccli/commands/login_command.py` | `ewc login` command + `init_options` decorator + `init_command()` logic |
| `ewccli/ewccli.py` | Registers the `login` command, wires `@init_options` |
| `ewccli/utils.py` | `save_cli_profile()`, `load_cli_profile()`, `save_default_login_profile()`, `_resolve_profile()` — INI-based profile at `~/.ewccli/profiles` |
| `ewccli/configuration.py` | `EWCCLIConfiguration` class — all config constants (paths, URLs, images, flavors, site map) |
| `ewccli/backends/openstack/backend_ostack.py` | `OpenstackBackend` — `connect()` uses `v3applicationcredential` auth type |
| `ewccli/commands/commons_infra.py` | `connect_to_openstack_backend()` helper |
| `ewccli/commands/infra_command.py` | `ewc infra` group — loads profile, instantiates `OpenstackBackend`, calls `connect()` |
| `ewccli/commands/hub/hub_command.py` | `ewc hub deploy` — same pattern: loads profile, creates backend, connects |
| `ewccli/enums.py` | `Federee`, `Region` enums |
| `ewccli/tests/ewccli_login_test.py` | Tests for `check_and_generate_ssh_keys` |
| `ewccli/tests/ewccli_config_test.py` | Tests for `save_cli_profile`/`load_cli_profile` |

### Current login flow (what stays unchanged)

1. `ewc login` → `init_command()` in `login_command.py`
2. Interactive: select federee (RadioList), select region (RadioList), enter app cred id/secret (click.prompt), handle SSH keys
3. `save_default_login_profile()` + `save_cli_profile()` write INI to `~/.ewccli/profiles`
4. Downstream: `load_cli_profile()` reads the INI, `OpenstackBackend` uses app creds to connect

### What changes

- `init_options` gets a new `--keycloak` flag (and `--no-browser`)
- `init_command()` gets a new branch: when `--keycloak` is set, run the OIDC flow instead of prompting for app creds
- New package `ewccli/backends/keycloak/` with the OIDC logic
- `configuration.py` gets Keycloak config constants
- `save_cli_profile()` / `load_cli_profile()` optionally store/load OIDC tokens (for refresh)
- New `token_manager.py` handles silent token refresh with rotation
- `ewccli.py` `init()` function signature gains the new params

### What does NOT change

- Profile INI format (new optional keys are additive)
- `OpenstackBackend` and its `connect()` method
- `connect_to_openstack_backend()` helper
- `load_cli_profile()` return dict shape (new optional keys only)
- All downstream commands (`infra`, `hub`) — they read app creds from the profile as before

---

## Task Breakdown

### Task 1: Add Keycloak/OIDC configuration constants

**Objective:** Add config values for Keycloak URL, realm, client_id, portal API URL, scope, and callback timeout to `EWCCLIConfiguration`.

**Files:**
- Modify: `ewccli/configuration.py` (add after line 31, the `EWC_CLI_DEFAULT_FEDEREE` line)

**Step 1: Add config constants**

Add these class attributes to `EWCCLIConfiguration`:

```python
    # Keycloak / OIDC configuration
    EWC_CLI_KEYCLOAK_URL = os.getenv(
        "EWC_CLI_KEYCLOAK_URL", "https://auth.europeanweather.cloud"
    )
    EWC_CLI_KEYCLOAK_REALM = os.getenv("EWC_CLI_KEYCLOAK_REALM", "ewc")
    EWC_CLI_KEYCLOAK_CLIENT_ID = os.getenv("EWC_CLI_KEYCLOAK_CLIENT_ID", "ewccli")
    EWC_CLI_KEYCLOAK_SCOPE = os.getenv("EWC_CLI_KEYCLOAK_SCOPE", "openid profile email")
    EWC_CLI_PORTAL_API_URL = os.getenv(
        "EWC_CLI_PORTAL_API_URL", "https://europeanweather.cloud"
    )
    EWC_CLI_OIDC_CALLBACK_TIMEOUT = int(
        os.getenv("EWC_CLI_OIDC_CALLBACK_TIMEOUT", "300")
    )
```

**Step 2: Verify**

Run: `python -c "from ewccli.configuration import config; print(config.EWC_CLI_KEYCLOAK_URL, config.EWC_CLI_KEYCLOAK_CLIENT_ID)"`
Expected: prints the default URL and `ewccli`.

**Step 3: Commit**

```bash
git add ewccli/configuration.py
git commit -m "feat: add Keycloak/OIDC configuration constants"
```

---

### Task 2: Create PKCE utilities module

**Objective:** Create a module that generates PKCE code_verifier, code_challenge (S256), and a random state token.

**Files:**
- Create: `ewccli/backends/keycloak/__init__.py` (empty)
- Create: `ewccli/backends/keycloak/pkce.py`

**Step 1: Write failing test**

Create `ewccli/tests/test_keycloak_pkce.py`:

```python
"""Tests for PKCE utilities."""
import base64
import hashlib

from ewccli.backends.keycloak.pkce import generate_pkce_pair, generate_state


def test_generate_pkce_pair_returns_verifier_and_challenge():
    verifier, challenge = generate_pkce_pair()
    assert isinstance(verifier, str)
    assert isinstance(challenge, str)
    assert len(verifier) >= 43
    assert len(verifier) <= 128
    # Challenge must be base64url(SHA256(verifier)) without padding
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    assert challenge == expected


def test_generate_pkce_pair_is_random():
    v1, c1 = generate_pkce_pair()
    v2, c2 = generate_pkce_pair()
    assert v1 != v2
    assert c1 != c2


def test_generate_state_is_random_string():
    s1 = generate_state()
    s2 = generate_state()
    assert isinstance(s1, str)
    assert len(s1) >= 32
    assert s1 != s2
```

**Step 2: Run test to verify failure**

Run: `pytest ewccli/tests/test_keycloak_pkce.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ewccli.backends.keycloak.pkce'`

**Step 3: Implement pkce.py**

```python
"""PKCE (Proof Key for Code Exchange) utilities for OIDC flows."""

import base64
import hashlib
import secrets


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and its S256 code_challenge.

    Returns:
        A tuple of (code_verifier, code_challenge). The verifier is a
        random URL-safe string of 43-128 chars. The challenge is
        base64url(SHA256(verifier)) without padding.
    """
    # Generate 32 random bytes -> 43 base64url chars (min length per RFC 7636)
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(32))
        .decode("ascii")
        .rstrip("=")
    )
    # S256 challenge
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def generate_state() -> str:
    """Generate a random state token for CSRF protection in OIDC flows."""
    return secrets.token_urlsafe(32)
```

**Step 4: Run test to verify pass**

Run: `pytest ewccli/tests/test_keycloak_pkce.py -v`
Expected: PASS — 3 passed

**Step 5: Commit**

```bash
git add ewccli/backends/keycloak/__init__.py ewccli/backends/keycloak/pkce.py ewccli/tests/test_keycloak_pkce.py
git commit -m "feat: add PKCE utilities for OIDC flows"
```

---

### Task 3: Create the OIDC callback HTTP server

**Objective:** Create a lightweight HTTP server that listens on a random loopback port, receives the OIDC authorization code callback, and returns it to the main thread.

**Files:**
- Create: `ewccli/backends/keycloak/callback_server.py`

**Step 1: Write failing test**

Create `ewccli/tests/test_keycloak_callback_server.py`:

```python
"""Tests for the OIDC callback server."""
import time
import urllib.request

from ewccli.backends.keycloak.callback_server import CallbackServer


def test_callback_server_receives_code():
    server = CallbackServer(expected_state="mystate")
    server.start()

    # Simulate browser redirect
    url = f"http://127.0.0.1:{server.port}/callback?code=mycode&state=mystate"
    urllib.request.urlopen(url, timeout=5)

    # Wait for the server to process
    result = server.wait_for_callback(timeout=5)
    server.stop()

    assert result is not None
    code, state = result
    assert code == "mycode"
    assert state == "mystate"


def test_callback_server_rejects_wrong_state():
    server = CallbackServer(expected_state="correct")
    server.start()

    url = f"http://127.0.0.1:{server.port}/callback?code=mycode&state=wrong"
    urllib.request.urlopen(url, timeout=5)

    result = server.wait_for_callback(timeout=3)
    server.stop()

    # Should return None or raise — state mismatch means no valid callback
    assert result is None


def test_callback_server_timeout():
    server = CallbackServer(expected_state="mystate")
    server.start()

    result = server.wait_for_callback(timeout=1)
    server.stop()

    assert result is None


def test_callback_server_port_is_assigned():
    server = CallbackServer(expected_state="mystate")
    server.start()
    assert server.port > 0
    server.stop()
```

**Step 2: Run test to verify failure**

Run: `pytest ewccli/tests/test_keycloak_callback_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement callback_server.py**

```python
"""Lightweight HTTP server to receive the OIDC authorization code callback."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, tuple
from urllib.parse import urlparse, parse_qs


_SUCCESS_HTML = (
    b"<html><body style='font-family:sans-serif;text-align:center;padding:50px'>"
    b"<h2>&#9989; Authentication successful!</h2>"
    b"<p>You can close this browser tab and return to your terminal.</p>"
    b"</body></html>"
)

_ERROR_HTML = (
    b"<html><body style='font-family:sans-serif;text-align:center;padding:50px'>"
    b"<h2>&#10060; Authentication failed</h2>"
    b"<p>State mismatch. Please try again.</p>"
    b"</body></html>"
)


class CallbackServer:
    """HTTP server that listens for the OIDC redirect callback on localhost.

    Usage:
        server = CallbackServer(expected_state="...")
        server.start()
        # ... open browser to auth URL ...
        result = server.wait_for_callback(timeout=300)
        server.stop()
    """

    def __init__(self, expected_state: str):
        self._expected_state = expected_state
        self._result: Optional[tuple[str, str]] = None
        self._error: Optional[str] = None
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0

    def start(self) -> None:
        """Start the server on a random loopback port."""
        handler = self._make_handler()
        self._httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Shut down the server."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=2)

    def wait_for_callback(self, timeout: float = 300) -> Optional[tuple[str, str]]:
        """Block until the callback is received or timeout.

        Returns (code, state) on success, or None on timeout/error.
        """
        if self._thread is None:
            return None
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            return None  # timed out
        return self._result

    @property
    def error(self) -> Optional[str]:
        """Return error description if one occurred."""
        return self._error

    @property
    def redirect_uri(self) -> str:
        """The redirect_uri to pass to the authorization endpoint."""
        return f"http://127.0.0.1:{self.port}/callback"

    def _make_handler(self):
        """Create a request handler class bound to this server instance."""

        expected_state = self._expected_state
        outer = self  # closure over the CallbackServer instance

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return

                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                state = params.get("state", [None])[0]

                if state != expected_state:
                    outer._error = "State mismatch"
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(_ERROR_HTML)
                    # Still stop the server so wait_for_callback returns
                    threading.Thread(
                        target=outer._httpd.shutdown, daemon=True
                    ).start()
                    return

                if code is None:
                    error = params.get("error", ["unknown"])[0]
                    outer._error = f"Authorization error: {error}"
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(_ERROR_HTML)
                    threading.Thread(
                        target=outer._httpd.shutdown, daemon=True
                    ).start()
                    return

                outer._result = (code, state)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(_SUCCESS_HTML)
                # Shut down the server in a separate thread so this handler
                # can finish sending the response first.
                threading.Thread(
                    target=outer._httpd.shutdown, daemon=True
                ).start()

            def log_message(self, format, *args):  # noqa: A002
                pass  # silence stderr logging

        return _Handler
```

**Step 4: Run test to verify pass**

Run: `pytest ewccli/tests/test_keycloak_callback_server.py -v`
Expected: PASS — 4 passed

**Step 5: Commit**

```bash
git add ewccli/backends/keycloak/callback_server.py ewccli/tests/test_keycloak_callback_server.py
git commit -m "feat: add OIDC callback HTTP server"
```

---

### Task 4: Create the OIDC client (auth URL + token exchange)

**Objective:** Build the authorization URL, exchange the authorization code for tokens, and optionally refresh tokens.

**Files:**
- Create: `ewccli/backends/keycloak/oidc_client.py`

**Step 1: Write failing test**

Create `ewccli/tests/test_keycloak_oidc_client.py`:

```python
"""Tests for the OIDC client."""
import pytest
from unittest.mock import patch, MagicMock

from ewccli.backends.keycloak.oidc_client import OIDCClient
from ewccli.backends.keycloak.pkce import generate_pkce_pair


@pytest.fixture
def oidc_client():
    return OIDCClient(
        keycloak_url="https://auth.example.com",
        realm="ewc",
        client_id="ewccli",
        scope="openid profile",
    )


def test_build_authorization_url(oidc_client):
    verifier, challenge = generate_pkce_pair()
    url = oidc_client.build_authorization_url(
        redirect_uri="http://127.0.0.1:12345/callback",
        code_challenge=challenge,
        state="mystate",
    )
    assert "https://auth.example.com/realms/ewc/protocol/openid-connect/auth" in url
    assert "client_id=ewccli" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "state=mystate" in url
    assert "scope=openid" in url


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

    # Verify the POST call
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "token" in call_args[0][0]  # URL contains /token
    assert call_args[1]["data"]["grant_type"] == "authorization_code"
    assert call_args[1]["data"]["code"] == "mycode"
    assert call_args[1]["data"]["code_verifier"] == "myverifier"


@patch("ewccli.backends.keycloak.oidc_client.requests.post")
def test_refresh_tokens(mock_post, oidc_client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_in": 3600,
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    tokens = oidc_client.refresh_tokens(refresh_token="old_refresh")

    assert tokens["access_token"] == "new_access"
    call_args = mock_post.call_args
    assert call_args[1]["data"]["grant_type"] == "refresh_token"
    assert call_args[1]["data"]["refresh_token"] == "old_refresh"
```

**Step 2: Run test to verify failure**

Run: `pytest ewccli/tests/test_keycloak_oidc_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement oidc_client.py**

```python
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
```

**Step 4: Run test to verify pass**

Run: `pytest ewccli/tests/test_keycloak_oidc_client.py -v`
Expected: PASS — 3 passed

**Step 5: Commit**

```bash
git add ewccli/backends/keycloak/oidc_client.py ewccli/tests/test_keycloak_oidc_client.py
git commit -m "feat: add OIDC client for Keycloak token exchange"
```

---

### Task 5: Create the portal API client

**Objective:** Call the EWC portal API with the OIDC access token to obtain OpenStack application credentials.

**Files:**
- Create: `ewccli/backends/keycloak/portal_client.py`

**Step 1: Write failing test**

Create `ewccli/tests/test_keycloak_portal_client.py`:

```python
"""Tests for the portal API client."""
import pytest
from unittest.mock import patch, MagicMock

from ewccli.backends.keycloak.portal_client import PortalClient, PortalCredentials


@pytest.fixture
def portal_client():
    return PortalClient(
        portal_api_url="https://europeanweather.cloud",
    )


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
```

**Step 2: Run test to verify failure**

Run: `pytest ewccli/tests/test_keycloak_portal_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement portal_client.py**

```python
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
```

**Step 4: Run test to verify pass**

Run: `pytest ewccli/tests/test_keycloak_portal_client.py -v`
Expected: PASS — 2 passed

**Step 5: Commit**

```bash
git add ewccli/backends/keycloak/portal_client.py ewccli/tests/test_keycloak_portal_client.py
git commit -m "feat: add portal API client for OpenStack credential exchange"
```

---

### Task 6: Create the Keycloak login orchestrator

**Objective:** Tie together PKCE, callback server, OIDC client, and portal client into a single `keycloak_login()` function that the login command calls.

**Files:**
- Create: `ewccli/backends/keycloak/keycloak_backend.py`

**Step 1: Write failing test**

Create `ewccli/tests/test_keycloak_backend.py`:

```python
"""Tests for the Keycloak login orchestrator."""
import pytest
from unittest.mock import patch, MagicMock

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


@patch("ewccli.backends.keycloak.keycloak_backend.webbrowser")
@patch("ewccli.backends.keycloak.keycloak_backend.PortalClient")
@patch("ewccli.backends.keycloak.keycloak_backend.OIDCClient")
@patch("ewccli.backends.keycloak.keycloak_backend.CallbackServer")
def test_keycloak_login_success(
    mock_cb_server_cls,
    mock_oidc_cls,
    mock_portal_cls,
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

    # Browser was opened
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
    mock_server.wait_for_callback.return_value = None  # timeout
    mock_server.error = None
    mock_cb_server_cls.return_value = mock_server

    from click import ClickException

    with pytest.raises(ClickException, match="timed out|timeout"):
        keycloak_login(
            config=mock_config,
            open_browser=False,
        )
```

**Step 2: Run test to verify failure**

Run: `pytest ewccli/tests/test_keycloak_backend.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement keycloak_backend.py**

```python
"""Keycloak login orchestrator — ties PKCE, callback, OIDC, and portal together."""

import webbrowser
from dataclasses import dataclass
from typing import Optional

from click import ClickException
from rich.console import Console

from ewccli.backends.keycloak.callback_server import CallbackServer
from ewccli.backends.keycloak.oidc_client import OIDCClient
from ewccli.backends.keycloak.pkce import generate_pkce_pair, generate_state
from ewccli.backends.keycloak.portal_client import PortalClient
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)
_console = Console()


@dataclass
class KeycloakLoginResult:
    """Result of a successful Keycloak login."""

    application_credential_id: str
    application_credential_secret: str
    auth_url: str
    access_token: str
    refresh_token: Optional[str]
    id_token: Optional[str]
    expires_in: int
    federee: Optional[str] = None
    region: Optional[str] = None
    tenant_name: Optional[str] = None


def keycloak_login(
    config,
    open_browser: bool = True,
    federee: Optional[str] = None,
    region: Optional[str] = None,
) -> KeycloakLoginResult:
    """Run the full Keycloak OIDC login flow.

    1. Start a local callback server
    2. Build the authorization URL (PKCE)
    3. Print URL and optionally open browser
    4. Wait for callback
    5. Exchange code for tokens
    6. Call portal API for OpenStack credentials

    Args:
        config: EWCCLIConfiguration instance with Keycloak settings.
        open_browser: If True, attempt to open the browser automatically.
        federee: Optional federee to pass to the portal API.
        region: Optional region to pass to the portal API.

    Returns:
        KeycloakLoginResult with app creds and OIDC tokens.

    Raises:
        ClickException: On timeout, state mismatch, or API errors.
    """
    timeout = config.EWC_CLI_OIDC_CALLBACK_TIMEOUT

    # 1. Generate PKCE pair and state
    code_verifier, code_challenge = generate_pkce_pair()
    state = generate_state()

    # 2. Start callback server
    server = CallbackServer(expected_state=state)
    server.start()
    _LOGGER.debug(f"Callback server listening on port {server.port}")

    # 3. Build OIDC client and authorization URL
    oidc_client = OIDCClient(
        keycloak_url=config.EWC_CLI_KEYCLOAK_URL,
        realm=config.EWC_CLI_KEYCLOAK_REALM,
        client_id=config.EWC_CLI_KEYCLOAK_CLIENT_ID,
        scope=config.EWC_CLI_KEYCLOAK_SCOPE,
    )

    auth_url = oidc_client.build_authorization_url(
        redirect_uri=server.redirect_uri,
        code_challenge=code_challenge,
        state=state,
    )

    # 4. Print URL and optionally open browser
    _console.print(
        "\n[bold cyan]🔑 EWC Keycloak Login[/bold cyan]\n"
        "Open the following URL in your browser to authenticate:\n"
    )
    _console.print(f"[link={auth_url}]{auth_url}[/link]\n")

    if open_browser:
        try:
            webbrowser.open(auth_url)
            _console.print("[green]🌐 Browser opened automatically.[/green]")
        except Exception:
            _console.print(
                "[yellow]⚠️ Could not open browser automatically. "
                "Please copy the URL above manually.[/yellow]"
            )
    else:
        _console.print(
            "[yellow]📋 --no-browser: copy the URL above manually.[/yellow]"
        )

    _console.print(f"\n⏳ Waiting for authentication (timeout: {timeout}s)...")

    # 5. Wait for callback
    callback_result = server.wait_for_callback(timeout=timeout)
    server.stop()

    if callback_result is None:
        if server.error:
            raise ClickException(
                f"OIDC authentication failed: {server.error}"
            )
        raise ClickException(
            f"OIDC authentication timed out after {timeout} seconds. "
            "Please try again."
        )

    code, received_state = callback_result

    # 6. Exchange code for tokens
    try:
        tokens = oidc_client.exchange_code_for_tokens(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=f"http://127.0.0.1:{server.port}/callback",
        )
    except Exception as e:
        raise ClickException(
            f"Failed to exchange authorization code for tokens: {e}"
        )

    _console.print("[green]✅ Authentication successful![/green]")

    # 7. Fetch OpenStack credentials from portal
    portal_client = PortalClient(
        portal_api_url=config.EWC_CLI_PORTAL_API_URL,
    )

    try:
        creds = portal_client.fetch_openstack_credentials(
            access_token=tokens["access_token"],
            federee=federee,
            region=region,
        )
    except Exception as e:
        raise ClickException(
            f"Failed to fetch OpenStack credentials from EWC portal: {e}"
        )

    _console.print("[green]✅ OpenStack credentials obtained![/green]")

    return KeycloakLoginResult(
        application_credential_id=creds.application_credential_id,
        application_credential_secret=creds.application_credential_secret,
        auth_url=creds.auth_url,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        id_token=tokens.get("id_token"),
        expires_in=tokens.get("expires_in", 3600),
        federee=creds.federee,
        region=creds.region,
        tenant_name=creds.tenant_name,
    )
```

**Step 4: Run test to verify pass**

Run: `pytest ewccli/tests/test_keycloak_backend.py -v`
Expected: PASS — 2 passed

**Step 5: Commit**

```bash
git add ewccli/backends/keycloak/keycloak_backend.py ewccli/tests/test_keycloak_backend.py
git commit -m "feat: add Keycloak login orchestrator"
```

---

### Task 7: Extend profile storage for OIDC tokens

**Objective:** Add optional `keycloak_*` keys to `save_cli_profile()` and `load_cli_profile()` so OIDC tokens can be persisted for future refresh.

**Files:**
- Modify: `ewccli/utils.py` — `save_cli_profile()` (line ~104) and `load_cli_profile()` (line ~184)

**Step 1: Write failing test**

Add to `ewccli/tests/ewccli_config_test.py`:

```python
def test_save_and_load_profile_with_oidc_tokens(profile_file_path, ssh_paths):
    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee="EUMETSAT",
        region="ECIS-R1",
        tenant_name="TeamA",
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        application_credential_id="app-id",
        application_credential_secret="app-secret",
        keycloak_access_token="access123",
        keycloak_refresh_token="refresh456",
        keycloak_id_token="id789",
        keycloak_token_expires_in=3600,
        profiles_file_path=str(profile_file_path),
    )

    data = load_cli_profile(
        profile="eumetsat-ecis-r1-teama",
        profiles_file_path=str(profile_file_path),
    )

    assert data["keycloak_access_token"] == "access123"
    assert data["keycloak_refresh_token"] == "refresh456"
    assert data["keycloak_id_token"] == "id789"
    assert data["keycloak_token_expires_in"] == "3600"


def test_load_profile_without_oidc_tokens_returns_none(profile_file_path, ssh_paths):
    """Profiles saved without OIDC tokens should load fine with None."""
    ssh_private, ssh_public = ssh_paths

    save_cli_profile(
        federee="EUMETSAT",
        region="ECIS-R1",
        tenant_name="TeamA",
        ssh_private_key_path_to_save=ssh_private,
        ssh_public_key_path_to_save=ssh_public,
        application_credential_id="app-id",
        application_credential_secret="app-secret",
        profiles_file_path=str(profile_file_path),
    )

    data = load_cli_profile(
        profile="eumetsat-ecis-r1-teama",
        profiles_file_path=str(profile_file_path),
    )

    assert data.get("keycloak_access_token") is None
    assert data.get("keycloak_refresh_token") is None
```

**Step 2: Run test to verify failure**

Run: `pytest ewccli/tests/ewccli_config_test.py -v -k "oidc"`
Expected: FAIL — `TypeError: save_cli_profile() got an unexpected keyword argument 'keycloak_access_token'`

**Step 3: Modify save_cli_profile()**

In `ewccli/utils.py`, add new optional parameters to `save_cli_profile()`:

```python
def save_cli_profile(
    federee: str,
    region: str,
    tenant_name: str,
    ssh_private_key_path_to_save: str,
    ssh_public_key_path_to_save: str,
    profile: Optional[str] = None,
    token: Optional[str] = None,
    application_credential_id: Optional[str] = None,
    application_credential_secret: Optional[str] = None,
    keycloak_access_token: Optional[str] = None,
    keycloak_refresh_token: Optional[str] = None,
    keycloak_id_token: Optional[str] = None,
    keycloak_token_expires_in: Optional[int] = None,
    profiles_file_path: Path = ewc_hub_config.EWC_CLI_PROFILES_PATH,
) -> None:
```

In the "Sensitive" section of the function body (after the `application_credential_secret` block, around line 177), add:

```python
    if keycloak_access_token:
        cfg[resolved_profile]["keycloak_access_token"] = keycloak_access_token

    if keycloak_refresh_token:
        cfg[resolved_profile]["keycloak_refresh_token"] = keycloak_refresh_token

    if keycloak_id_token:
        cfg[resolved_profile]["keycloak_id_token"] = keycloak_id_token

    if keycloak_token_expires_in:
        cfg[resolved_profile]["keycloak_token_expires_in"] = str(
            keycloak_token_expires_in
        )
```

**Step 4: Modify load_cli_profile()**

In the return dict of `load_cli_profile()` (around line 362), add:

```python
        "keycloak_access_token": section.get("keycloak_access_token"),
        "keycloak_refresh_token": section.get("keycloak_refresh_token"),
        "keycloak_id_token": section.get("keycloak_id_token"),
        "keycloak_token_expires_in": section.get("keycloak_token_expires_in"),
```

**Step 5: Run test to verify pass**

Run: `pytest ewccli/tests/ewccli_config_test.py -v`
Expected: PASS — all tests pass (including existing ones — backward compatible)

**Step 6: Commit**

```bash
git add ewccli/utils.py ewccli/tests/ewccli_config_test.py
git commit -m "feat: extend profile storage for OIDC tokens"
```

---

### Task 8: Add `--keycloak` flag to login command options

**Objective:** Add the `--keycloak` and `--no-browser` CLI options to the `init_options` decorator.

**Files:**
- Modify: `ewccli/commands/login_command.py` — `init_options()` function (line ~126)

**Step 1: Add options to init_options**

In `init_options()`, add these options before the `return func` (after the `--profile` option, around line 219):

```python
    func = click.option(
        "--keycloak",
        is_flag=True,
        default=False,
        envvar="EWC_CLI_KEYCLOAK_LOGIN",
        help=(
            "Login via Keycloak OIDC (browser-based). "
            "Opens a browser for authentication and fetches "
            "OpenStack credentials automatically from the EWC portal. "
            "Can also be set via EWC_CLI_KEYCLOAK_LOGIN=1."
        ),
    )(func)
    func = click.option(
        "--no-browser",
        is_flag=True,
        default=False,
        help=(
            "Print the login URL instead of opening a browser. "
            "Useful for SSH sessions or headless environments."
        ),
    )(func)
```

**Step 2: Update the init() command in ewccli.py**

In `ewccli/ewccli.py`, update the `init()` function signature to accept the new params:

```python
@cli.command(name="login", help="Initialize configuration for EWC CLI.")
@init_options
def init(
    application_credential_id: str,
    application_credential_secret: str,
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    tenant_name: str,
    federee: str,
    region: str,
    profile: Optional[str] = None,
    keycloak: bool = False,
    no_browser: bool = False,
):
    """Login command."""
    init_command(
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
        ssh_public_key_path=ssh_public_key_path,
        ssh_private_key_path=ssh_private_key_path,
        tenant_name=tenant_name,
        federee=federee,
        profile=profile,
        region=region,
        keycloak=keycloak,
        no_browser=no_browser,
    )
```

**Step 3: Verify the CLI renders the new options**

Run: `ewc login --help`
Expected: shows `--keycloak` and `--no-browser` in help output.

**Step 4: Commit**

```bash
git add ewccli/commands/login_command.py ewccli/ewccli.py
git commit -m "feat: add --keycloak and --no-browser flags to ewc login"
```

---

### Task 9: Implement the Keycloak login path in init_command()

**Objective:** When `--keycloak` is set, run the OIDC flow instead of prompting for app creds. Integrate the result into the existing profile-saving logic.

**Files:**
- Modify: `ewccli/commands/login_command.py` — `init_command()` function (line ~386)

**Step 1: Update init_command() signature**

Change the function signature to accept the new params:

```python
def init_command(
    application_credential_id: str,
    application_credential_secret: str,
    ssh_public_key_path: str,
    ssh_private_key_path: str,
    tenant_name: str,
    federee: str,
    region: str,
    profile: str = None,
    keycloak: bool = False,
    no_browser: bool = False,
):
    """EWC CLI Login."""
```

**Step 2: Add the Keycloak branch**

After the `resolved_profile` computation (line ~422) and the profile-exists check, but before the SSH key handling (line ~444), insert the Keycloak login branch:

```python
    # --- Keycloak OIDC login path ---
    keycloak_access_token = None
    keycloak_refresh_token = None
    keycloak_id_token = None
    keycloak_token_expires_in = None

    if keycloak:
        from ewccli.backends.keycloak.keycloak_backend import keycloak_login

        kc_result = keycloak_login(
            config=ewc_hub_config,
            open_browser=not no_browser,
            federee=federee,
            region=region,
        )

        # Use credentials from the portal
        application_credential_id = kc_result.application_credential_id
        application_credential_secret = kc_result.application_credential_secret

        # If the portal returned federee/region/tenant_name, use them
        if kc_result.federee:
            federee = kc_result.federee
        if kc_result.region:
            region = kc_result.region
        if kc_result.tenant_name:
            tenant_name = kc_result.tenant_name

        # Store OIDC tokens for future refresh
        keycloak_access_token = kc_result.access_token
        keycloak_refresh_token = kc_result.refresh_token
        keycloak_id_token = kc_result.id_token
        keycloak_token_expires_in = kc_result.expires_in

        # Skip the openstack_config_available / manual credential prompts below
        # since we have the credentials already.
    elif not federee:
```

Then the existing `elif not federee:` / `if not region:` interactive selection blocks follow naturally.

The existing block at lines 451-478 (cloud.yaml check and manual credential prompt) should be wrapped so it only runs when `keycloak` is False:

```python
    if not keycloak:
        if openstack_config_available():
            console.print(
                "🔑 [bold green]Openstack cloud.yaml found at ~/.config/openstack/clouds.yaml[/bold green]"
                " – skipping Openstack ID and secret requirements."
            )
            application_credential_id = ""
            application_credential_secret = ""

        elif not application_credential_id or not application_credential_secret:
            if not application_credential_id:
                application_credential_id = (
                    application_credential_id
                    or os.getenv("OS_APPLICATION_CREDENTIAL_ID")
                    or click.prompt(
                        "Enter OpenStack Application Credential ID", hide_input=True
                    )
                )

            if not application_credential_secret:
                application_credential_secret = (
                    application_credential_secret
                    or os.getenv("OS_APPLICATION_CREDENTIAL_SECRET")
                    or click.prompt(
                        "Enter OpenStack Application Credential Secret", hide_input=True
                    )
                )
```

**Step 3: Pass OIDC tokens to save_cli_profile**

At the bottom of `init_command()`, update both `save_default_login_profile()` and `save_cli_profile()` calls to include the OIDC token params:

```python
    save_default_login_profile(
        federee=federee,
        region=region,
        tenant_name=tenant_name,
        ssh_private_key_path_to_save=ssh_private_key_path_to_save,
        ssh_public_key_path_to_save=ssh_public_key_path_to_save,
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
    )

    # Save config
    save_cli_profile(
        federee=federee,
        region=region,
        tenant_name=tenant_name,
        ssh_private_key_path_to_save=ssh_private_key_path_to_save,
        ssh_public_key_path_to_save=ssh_public_key_path_to_save,
        profile=profile,
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
        keycloak_access_token=keycloak_access_token,
        keycloak_refresh_token=keycloak_refresh_token,
        keycloak_id_token=keycloak_id_token,
        keycloak_token_expires_in=keycloak_token_expires_in,
    )
```

Note: `save_default_login_profile()` does not need the OIDC tokens — it's just a fallback default. Only the explicit `save_cli_profile()` call gets the tokens.

**Step 4: Verify the command works**

Run: `ewc login --help`
Expected: help text shows `--keycloak` flag.

Run: `ewc login --keycloak --dry-run` (if dry-run is available) or just verify it doesn't crash on import.

**Step 5: Commit**

```bash
git add ewccli/commands/login_command.py
git commit -m "feat: implement Keycloak OIDC login path in ewc login"
```

---

### Task 10: Handle missing tenant_name in Keycloak flow

**Objective:** The current `init_command` requires `tenant_name` (it's `prompt=True, required=True` in `init_options`). When using `--keycloak`, the tenant_name may come from the portal API instead. We need to make `tenant_name` optional when `--keycloak` is used.

**Files:**
- Modify: `ewccli/commands/login_command.py` — `init_options()` `--tenant-name` option (line ~128)

**Step 1: Make tenant_name not prompted when keycloak is used**

Change the `--tenant-name` option from `prompt=True, required=True` to `required=False` (the prompt will be handled in `init_command()` when not using keycloak):

```python
    func = click.option(
        "--tenant-name",
        envvar="EWC_CLI_LOGIN_TENANT_NAME",
        required=False,
        callback=validate_tenant_name,
        help=(
            "Name of your tenancy in EWC, used to identify cloud configurations.\n"
            "Must follow the format: 'part1-part2-part3' (e.g. 'demo-user-eu'), "
            "where each part is alphanumeric and separated by dashes.\n"
            "Required when not using --keycloak. "
            "Can also be set via the EWC_CLI_LOGIN_TENANT_NAME environment variable."
        ),
    )(func)
```

**Step 2: Add prompt in init_command when tenant_name is missing and not keycloak**

In `init_command()`, after the keycloak branch, add:

```python
    if not keycloak and not tenant_name:
        tenant_name = click.prompt("Tenant name")
```

And move the `validate_tenant_name` validation to after this prompt (or rely on the callback which already ran for CLI-provided values; for prompted values, call it manually):

```python
    if not keycloak and tenant_name:
        # Re-validate since it may have been prompted
        import re
        pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
        if not re.match(pattern, tenant_name):
            raise click.BadParameter(
                "Config name must be exactly 3 alphanumeric parts separated by dashes."
            )
```

**Step 3: Verify**

Run: `ewc login --help`
Expected: `--tenant-name` no longer shows as required.

**Step 4: Commit**

```bash
git add ewccli/commands/login_command.py
git commit -m "fix: make tenant_name optional when using --keycloak login"
```

---

### Task 11: Update the README documentation

**Objective:** Document the new `--keycloak` login flow in the README.

**Files:**
- Modify: `README.md` — "Login to prepare the environment" section (line ~178)

**Step 1: Add Keycloak login documentation**

After the existing `ewc login` section, add:

```markdown
### Login with Keycloak (OIDC)

Instead of manually entering OpenStack application credentials, you can authenticate via Keycloak:

```bash
ewc login --keycloak
```

This will:
1. Open a browser window for Keycloak authentication
2. After successful login, fetch OpenStack credentials from the EWC portal
3. Save everything to your profile

If you're on a headless machine or SSH session, use `--no-browser` to print the URL instead:

```bash
ewc login --keycloak --no-browser
```

You can still combine with other flags:

```bash
ewc login --keycloak --federee EUMETSAT --region ECIS-R1
```

**Configuration:**

The Keycloak settings can be overridden via environment variables:

| Variable | Default | Description |
|---|---|---|
| `EWC_CLI_KEYCLOAK_URL` | `https://auth.europeanweather.cloud` | Keycloak server URL |
| `EWC_CLI_KEYCLOAK_REALM` | `ewc` | Keycloak realm |
| `EWC_CLI_KEYCLOAK_CLIENT_ID` | `ewccli` | OIDC client ID |
| `EWC_CLI_PORTAL_API_URL` | `https://europeanweather.cloud` | EWC portal API URL |
| `EWC_CLI_OIDC_CALLBACK_TIMEOUT` | `300` | Callback wait timeout (seconds) |
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document Keycloak OIDC login"
```

---

### Task 12: Run full test suite and fix any regressions

**Objective:** Ensure all existing tests still pass and new tests are green.

**Step 1: Run all tests**

```bash
cd /home/kamil/projects/ewccli
pytest ewccli/tests/ -v
```

**Step 2: Fix any failures**

If existing tests fail due to the `init_command` signature change (e.g., tests that call `init_command` directly), update the test calls to include `keycloak=False, no_browser=False`.

**Step 3: Verify CLI still works**

```bash
ewc login --help
ewc version
```

**Step 4: Final commit if fixes were needed**

```bash
git add -A
git commit -m "test: fix regressions from Keycloak login integration"
```

---

## File Summary

### New files (7)

| File | Purpose |
|---|---|
| `ewccli/backends/keycloak/__init__.py` | Package init |
| `ewccli/backends/keycloak/pkce.py` | PKCE code_verifier/code_challenge generation |
| `ewccli/backends/keycloak/callback_server.py` | Loopback HTTP server for OIDC callback |
| `ewccli/backends/keycloak/oidc_client.py` | Auth URL builder + token exchange/refresh |
| `ewccli/backends/keycloak/portal_client.py` | Portal API client → app creds |
| `ewccli/backends/keycloak/keycloak_backend.py` | Orchestrator (`keycloak_login()`) |
| `ewccli/tests/test_keycloak_*.py` (4 files) | Tests for each module |

### Modified files (4)

| File | Changes |
|---|---|
| `ewccli/configuration.py` | +6 config constants for Keycloak/OIDC |
| `ewccli/utils.py` | `save_cli_profile` / `load_cli_profile` gain optional `keycloak_*` params |
| `ewccli/commands/login_command.py` | `init_options` gets `--keycloak`/`--no-browser`; `init_command` gets OIDC branch; `--tenant-name` made optional |
| `ewccli/ewccli.py` | `init()` signature updated with new params |
| `README.md` | Documentation for `--keycloak` |

### Unchanged files (all downstream)

- `ewccli/backends/openstack/backend_ostack.py` — `OpenstackBackend` and `connect()` untouched
- `ewccli/commands/commons_infra.py` — `connect_to_openstack_backend()` untouched
- `ewccli/commands/infra_command.py` — reads profile as before
- `ewccli/commands/hub/hub_command.py` — reads profile as before

---

## Token Refresh Strategy

### Industry best practices applied

- **Short-lived access tokens** (5 min default): if stolen, the abuse window is small
- **Longer-lived refresh tokens** (7 days max): user authenticates once, CLI silently refreshes
- **Refresh token rotation** (RFC 9700): each refresh returns a NEW refresh_token and invalidates the old one. The CLI must immediately overwrite the stored refresh_token. This detects theft — if someone steals and uses a refresh_token, the legitimate CLI's next refresh fails.
- **Proactive refresh**: check expiry before use, not after a 401. Refresh if the access token is expired or about to expire (within a 60s skew window).

### Token storage fields in the profile

| Key | Type | Description |
|---|---|---|
| `keycloak_access_token` | str | Current OIDC access token |
| `keycloak_refresh_token` | str | Current refresh token (rotated on each refresh) |
| `keycloak_id_token` | str | ID token (JWT with user claims) |
| `keycloak_token_expires_at` | str (ISO 8601) | Absolute expiry timestamp of the access token. Stored as ISO 8601 UTC so no "now + expires_in" recalculation is needed. |

### Refresh flow

```
get_valid_access_token(profile):
    1. Parse keycloak_token_expires_at from profile
    2. If not expired (with 60s skew): return stored access_token
    3. If expired and no refresh_token: raise ClickException("Session expired. Run: ewc login --keycloak")
    4. If expired and refresh_token exists:
       a. Call oidc_client.refresh_tokens(refresh_token)
       b. Receive new access_token + new refresh_token (rotation)
       c. Calculate new expires_at = now + expires_in
       d. Update profile INI with new tokens + expires_at
       e. Return new access_token
    5. If refresh fails (HTTP 400 invalid_grant):
       raise ClickException("Session expired. Run: ewc login --keycloak")
```

### Recommended Keycloak realm settings

- Access token lifespan: 5 min
- Client: public (PKCE, no client secret)
- Refresh token: enabled
- Revoke Refresh Token: ON (rotation)
- Refresh Token Max Reuse: 0 (single-use)
- SSO Session Idle Timeout: 30 min
- SSO Session Max Lifespan: 7 days

This means: user authenticates once, the CLI silently refreshes for up to 7 days, then they see "Session expired, run ewc login --keycloak".

---

## Risks and Tradeoffs

1. **Portal API contract is assumed.** The endpoint path (`/api/v1/credentials/openstack`), request shape, and response shape are all assumed. When the real API is known, only `portal_client.py` needs updating — the rest of the flow is contract-agnostic.

2. **OIDC tokens stored in plaintext INI.** The `keycloak_access_token` and `keycloak_refresh_token` are stored in `~/.ewccli/profiles` in plaintext, same as the existing `application_credential_secret`. This is consistent but not ideal. A future enhancement could use the OS keyring.

3. **Loopback callback server.** The callback server binds to `127.0.0.1` on a random port. If the user is behind a strict firewall or in a container without loopback, this won't work. The `--no-browser` flag helps with SSH sessions (user copies URL to local browser), but the callback still needs to reach the machine where the CLI is running. For pure headless/CI scenarios, a `--device-code` flow (RFC 8628) would be better — out of scope for this plan.

4. **`tenant_name` validation.** The existing `validate_tenant_name` callback enforces a 3-part dash-separated pattern. When the portal API returns a `tenant_name`, it may not match this pattern. The validation is skipped in the keycloak path (the callback only runs on CLI-provided values, and the keycloak branch sets tenant_name after validation). If the portal's tenant_name format differs, it's stored as-is.

5. **Multiple federees.** A user may have projects on both EUMETSAT and ECMWF. The current `ewc login --keycloak` flow creates one profile per invocation. To support multiple federees, the user runs `ewc login --keycloak --federee ECMWF --profile ecmwf-profile` separately. The portal API would need to support the `federee`/`region` query params as described in the contract.

6. **Refresh token rotation atomicity.** If the CLI crashes between receiving a new refresh_token and writing it to the profile INI, the old refresh_token is already invalidated server-side. The user must re-authenticate. This is an accepted tradeoff of rotation — it's a rare edge case and the security benefit outweighs it.

---

## Open Questions (to resolve during implementation)

1. Does the portal API return `auth_url`, or should the CLI derive it from the `EWC_CLI_SITE_MAP` using the returned `federee`/`region`? If the portal returns it, we use it directly (more flexible). If not, we fall back to `EWC_CLI_SITE_MAP[federee][region]`.

2. Should `--keycloak` be the default in the future (i.e., `ewc login` with no flags triggers OIDC)? For now it's opt-in via the flag. Consider deprecating the manual flow once the portal API is stable.

3. Should the CLI create the application credential (via OpenStack API) if the portal only returns a project-scoped token? This would add a step: after OIDC login, use the token to authenticate to Keystone, then create an app cred via `openstack.identity.v3.application_credential`. This is more complex but removes the portal dependency. Out of scope for this plan.
