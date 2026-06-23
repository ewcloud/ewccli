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
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(32))
        .decode("ascii")
        .rstrip("=")
    )
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def generate_state() -> str:
    """Generate a random state token for CSRF protection in OIDC flows."""
    return secrets.token_urlsafe(32)
