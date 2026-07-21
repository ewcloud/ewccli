#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""kubelogin wrapper — runs the kubelogin binary to obtain an OIDC token.

kubelogin (https://github.com/int128/kubelogin) handles the browser-based
OIDC flow against Dex and prints an ExecCredential JSON to stdout. Tokens
are cached at ``~/.kube/cache/oidc-login/`` (~2h lifetime) so subsequent
calls are silent.
"""

import json
import re
import subprocess
import sys

from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


def get_kkp_token(issuer, client_id, client_secret, timeout=300):
    """Run kubelogin to get a kubermatic-audience token for KKP API auth.

    kubelogin --skip-open-browser prints "Please visit http://localhost:8000/"
    to stderr, waits for browser auth, outputs ExecCredential JSON to stdout.
    Token cached at ~/.kube/cache/oidc-login/ (~2h).

    Returns:
        The ``status.token`` string from the ExecCredential.

    Raises:
        RuntimeError: If kubelogin exits non-zero or stdout is not valid
            ExecCredential JSON.
    """
    result = subprocess.run(
        [
            "kubelogin",
            "get-token",
            f"--oidc-issuer-url={issuer}",
            f"--oidc-client-id={client_id}",
            f"--oidc-client-secret={client_secret}",
            "--oidc-extra-scope=email",
            "--oidc-extra-scope=groups",
            "--skip-open-browser",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        m = re.search(r"(https?://\S+)", result.stderr)
        if m:
            print(f"Open this URL to authenticate:\n{m.group(1)}", file=sys.stderr)
        raise RuntimeError(f"kubelogin failed: {result.stderr[:200]}")

    try:
        cred = json.loads(result.stdout)
        return cred["status"]["token"]
    except (ValueError, KeyError) as e:
        raise RuntimeError(
            f"kubelogin returned invalid ExecCredential JSON: {e}"
        ) from e
