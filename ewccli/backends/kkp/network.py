#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Network setup for KKP user-cluster access.

Ensures the kubelogin binary is installed. The user-cluster apiserver
must be directly reachable from the host running ewccli — no tunnel.
"""

import os
import subprocess

from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)

_KUBELOGIN_URL = (
    "https://github.com/int128/kubelogin/releases/download/"
    "v1.36.2/kubelogin_linux_amd64.zip"
)


def ensure_kubelogin():
    """Check kubelogin is installed; download if missing. Idempotent."""
    r = subprocess.run(["which", "kubelogin"], capture_output=True)
    if r.returncode == 0:
        return

    bin_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(bin_dir, exist_ok=True)

    _LOGGER.info("Installing kubelogin to %s", bin_dir)
    subprocess.run(
        ["curl", "-L", "-o", "/tmp/kubelogin.zip", _KUBELOGIN_URL],
        check=True,
    )
    subprocess.run(
        ["unzip", "-o", "/tmp/kubelogin.zip", "-d", bin_dir],
        check=True,
    )
    link = f"{bin_dir}/kubectl-oidc_login"
    if not os.path.exists(link):
        os.symlink(f"{bin_dir}/kubelogin", link)
