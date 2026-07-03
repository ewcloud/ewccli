#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Network setup for KKP user-cluster access.

User-cluster apiservers use Tunneling expose strategy — not directly
reachable. This module ensures:
  1. An SSH tunnel (localhost:6443 → apiserver via jump host) is up.
  2. /etc/hosts maps the apiserver hostname to 127.0.0.1 (TLS SNI).
  3. The kubelogin binary is installed.

All functions are idempotent.
"""

import os
import subprocess

from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)

_KUBELOGIN_URL = (
    "https://github.com/int128/kubelogin/releases/download/"
    "v1.36.2/kubelogin_linux_amd64.zip"
)


def ensure_tunnel(jump_host, tunnel_host, apiserver_ip, port=6443):
    """Start SSH tunnel if not already listening. Idempotent.

    ssh -f -J {jump_host} -L {port}:{apiserver_ip}:{port} -N {tunnel_host}
    """
    r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
    if f":{port} " in r.stdout:
        _LOGGER.debug("SSH tunnel on port %s already up", port)
        return

    _LOGGER.info("Starting SSH tunnel: localhost:%s -> %s:%s", port, apiserver_ip, port)
    subprocess.run(
        [
            "ssh",
            "-f",
            "-J",
            jump_host,
            "-L",
            f"{port}:{apiserver_ip}:{port}",
            "-N",
            tunnel_host,
        ],
        check=True,
        timeout=30,
    )


def ensure_hosts_entry(hostname):
    """Add ``127.0.0.1 <hostname>`` to /etc/hosts. Needs sudo. Idempotent."""
    try:
        with open("/etc/hosts") as f:
            if hostname in f.read():
                _LOGGER.debug("/etc/hosts already has %s", hostname)
                return
    except PermissionError:
        pass  # fall through to sudo path

    _LOGGER.info("Adding %s to /etc/hosts (sudo required)", hostname)
    subprocess.run(
        f'echo "127.0.0.1 {hostname}" | sudo tee -a /etc/hosts',
        shell=True,
        check=True,
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
