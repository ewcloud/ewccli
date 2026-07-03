#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Post-process KKP OIDC kubeconfigs.

KKP returns kubeconfigs with the deprecated ``auth-provider: oidc`` block.
kubelogin's exec plugin (``kubectl oidc-login get-token``) is the modern
replacement. This rewrites the auth-provider into an exec block so
``kubectl`` / the kubernetes client transparently refreshes tokens.
"""

import yaml


def patch_kubeconfig(raw_yaml: str) -> str:
    """Replace deprecated auth-provider block with kubelogin exec block.

    Walks all users in the kubeconfig; for each user with
    ``auth-provider.name == "oidc"``, the auth-provider config is mapped
    to exec-plugin arguments and the auth-provider key is removed.

    Returns:
        The patched kubeconfig as YAML.
    """
    cfg = yaml.safe_load(raw_yaml)
    for user in cfg.get("users", []):
        u = user.get("user", {})
        ap = u.get("auth-provider")
        if ap and ap.get("name") == "oidc":
            c = ap.get("config", {})
            u.pop("auth-provider", None)
            u["exec"] = {
                "apiVersion": "client.authentication.k8s.io/v1",
                "command": "kubectl",
                "args": [
                    "oidc-login",
                    "get-token",
                    f"--oidc-issuer-url={c.get('idp-issuer-url', '')}",
                    f"--oidc-client-id={c.get('client-id', '')}",
                    f"--oidc-client-secret={c.get('client-secret', '')}",
                    "--oidc-extra-scope=email",
                    "--oidc-extra-scope=groups",
                ],
                "interactiveMode": "IfAvailable",
            }
    return yaml.dump(cfg, default_flow_style=False)
