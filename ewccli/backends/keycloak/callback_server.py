"""Lightweight HTTP server to receive the OIDC authorization code callback."""

import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
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
    b"<p>State mismatch or error. Please try again.</p>"
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

    def __init__(self, expected_state: str, port: int = 0):
        self._expected_state = expected_state
        self._result: Optional[tuple[str, str]] = None
        self._error: Optional[str] = None
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._requested_port = port
        self.port: int = 0

    def start(self) -> None:
        """Start the server on a loopback port."""
        handler = self._make_handler()
        self._httpd = HTTPServer(("127.0.0.1", self._requested_port), handler)
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

        Uses a polling loop instead of a blocking thread.join() so that
        SIGINT (Ctrl+C) can interrupt the wait on the main thread.
        """
        if self._thread is None:
            return None

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._result is not None or self._error is not None:
                break
            if not self._thread.is_alive():
                break
            time.sleep(0.2)

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
