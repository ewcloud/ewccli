"""Keycloak login orchestrator — OIDC auth code + PKCE flow.

Returns an ephemeral access token. No tokens are persisted here; the caller
decides what to do with the access token (e.g. exchange it for OpenBao
credentials).
"""

import webbrowser
from dataclasses import dataclass
from typing import Optional

from click import ClickException
from rich.console import Console

from ewccli.backends.keycloak.callback_server import CallbackServer
from ewccli.backends.keycloak.oidc_client import OIDCClient
from ewccli.backends.keycloak.pkce import generate_pkce_pair, generate_state
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)
_console = Console()


@dataclass
class KeycloakLoginResult:
    """Result of a successful Keycloak login."""

    access_token: str


def keycloak_login(
    config,
    open_browser: bool = True,
    federee: Optional[str] = None,
) -> KeycloakLoginResult:
    """Run the full Keycloak OIDC login flow.

    1. Generate PKCE pair and state
    2. Start a local callback server
    3. Build the authorization URL (PKCE)
    4. Print URL and optionally open browser
    5. Wait for callback
    6. Exchange code for tokens

    Args:
        config: EWCCLIConfiguration instance with Keycloak settings.
        open_browser: If True, attempt to open the browser automatically.
        federee: Optional federee (unused by the OIDC flow itself, kept for
            API compatibility).

    Returns:
        KeycloakLoginResult with the ephemeral access token.

    Raises:
        ClickException: On timeout, state mismatch, or API errors.
    """
    timeout = config.EWC_CLI_OIDC_CALLBACK_TIMEOUT

    # 1. Generate PKCE pair and state
    code_verifier, code_challenge = generate_pkce_pair()
    state = generate_state()

    # 2. Start callback server
    server = CallbackServer(
        expected_state=state,
        port=config.EWC_CLI_OIDC_CALLBACK_PORT,
    )
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
    try:
        callback_result = server.wait_for_callback(timeout=timeout)
    except KeyboardInterrupt:
        server.stop()
        raise ClickException("Authentication cancelled by user.")
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

    return KeycloakLoginResult(access_token=tokens["access_token"])
