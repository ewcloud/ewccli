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
