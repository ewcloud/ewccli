"""Keycloak login orchestrator — ties PKCE, callback, OIDC, and portal together."""

import os
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
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


def _compute_expires_at(expires_in: int) -> str:
    """Compute the absolute expiry timestamp from an expires_in value."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return expiry.isoformat()


@dataclass
class KeycloakLoginResult:
    """Result of a successful Keycloak login."""

    application_credential_id: str
    application_credential_secret: str
    auth_url: str
    access_token: str
    refresh_token: Optional[str]
    id_token: Optional[str]
    token_expires_at: str
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
        "\n[bold cyan]Keycloak Login[/bold cyan]\n"
        "Open the following URL in your browser to authenticate:\n"
    )
    _console.print(f"[link={auth_url}]{auth_url}[/link]\n")

    if open_browser:
        try:
            webbrowser.open(auth_url)
            _console.print("[green]Browser opened automatically.[/green]")
        except Exception:
            _console.print(
                "[yellow]Could not open browser automatically. "
                "Please copy the URL above manually.[/yellow]"
            )
    else:
        _console.print(
            "[yellow]--no-browser: copy the URL above manually.[/yellow]"
        )

    _console.print(f"\nWaiting for authentication (timeout: {timeout}s)...")

    # 5. Wait for callback
    callback_result = server.wait_for_callback(timeout=timeout)
    redirect_uri = server.redirect_uri
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
            redirect_uri=redirect_uri,
        )
    except Exception as e:
        raise ClickException(
            f"Failed to exchange authorization code for tokens: {e}"
        )

    _console.print("[green]Authentication successful![/green]")

    # 7. Fetch OpenStack credentials from portal (if configured)
    expires_in = tokens.get("expires_in", 300)
    token_expires_at = _compute_expires_at(expires_in)

    portal_url = getattr(config, "EWC_CLI_PORTAL_API_URL", "")
    if not portal_url:
        # Portal not configured — store OIDC tokens only, fall through to
        # the existing credential path (cloud.yaml, env vars, or manual prompt).
        _console.print(
            "[yellow]Portal API not configured — skipping OpenStack credential fetch. "
            "Set EWC_CLI_PORTAL_API_URL to enable automatic credential retrieval.[/yellow]"
        )
        return KeycloakLoginResult(
            application_credential_id="",
            application_credential_secret="",
            auth_url="",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            id_token=tokens.get("id_token"),
            token_expires_at=token_expires_at,
            federee=federee,
            region=region,
            tenant_name=None,
        )

    portal_client = PortalClient(
        portal_api_url=portal_url,
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

    _console.print("[green]OpenStack credentials obtained![/green]")

    return KeycloakLoginResult(
        application_credential_id=creds.application_credential_id,
        application_credential_secret=creds.application_credential_secret,
        auth_url=creds.auth_url,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        id_token=tokens.get("id_token"),
        token_expires_at=token_expires_at,
        federee=creds.federee,
        region=creds.region,
        tenant_name=creds.tenant_name,
    )
