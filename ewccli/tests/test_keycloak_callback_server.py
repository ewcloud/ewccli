"""Tests for the OIDC callback server."""
import urllib.request
import urllib.error

from ewccli.backends.keycloak.callback_server import CallbackServer


def test_callback_server_receives_code():
    server = CallbackServer(expected_state="mystate")
    server.start()

    url = f"http://127.0.0.1:{server.port}/callback?code=mycode&state=mystate"
    urllib.request.urlopen(url, timeout=5)

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
    # Server returns 400 on state mismatch — urlopen raises HTTPError
    try:
        urllib.request.urlopen(url, timeout=5)
    except urllib.error.HTTPError:
        pass  # expected — the 400 response is the correct behavior

    result = server.wait_for_callback(timeout=3)
    server.stop()

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


def test_callback_server_redirect_uri():
    server = CallbackServer(expected_state="mystate")
    server.start()
    assert server.redirect_uri == f"http://127.0.0.1:{server.port}/callback"
    server.stop()
