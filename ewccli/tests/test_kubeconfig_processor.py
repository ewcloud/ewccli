"""Tests for the kubeconfig post-processor (auth-provider -> exec)."""

import yaml

from ewccli.backends.kkp.kubeconfig_processor import (
    patch_kubeconfig,
    extract_hostname,
)


def _raw_kubeconfig():
    return """
apiVersion: v1
kind: Config
clusters:
- name: my-cluster
  cluster:
    server: https://abv9l8vmfm.kubermatic.k8s-val.eumetsat.europeanweather.cloud:6443
    certificate-authority-data: ABC
users:
- name: my-user
  user:
    auth-provider:
      name: oidc
      config:
        idp-issuer-url: https://k8s-val.eumetsat.europeanweather.cloud/dex
        client-id: kubermaticIssuer
        client-secret: buetTpb4Rnp0C5BgebuyGKS0CCXBtjFU
contexts:
- name: my-context
  context:
    cluster: my-cluster
    user: my-user
current-context: my-context
"""


def test_auth_provider_replaced_with_exec():
    patched = patch_kubeconfig(_raw_kubeconfig())
    cfg = yaml.safe_load(patched)

    user = cfg["users"][0]["user"]
    assert "auth-provider" not in user
    assert "exec" in user

    exec_block = user["exec"]
    assert exec_block["apiVersion"] == "client.authentication.k8s.io/v1"
    assert exec_block["command"] == "kubectl"
    assert exec_block["interactiveMode"] == "IfAvailable"


def test_exec_args_contain_oidc_config():
    patched = patch_kubeconfig(_raw_kubeconfig())
    cfg = yaml.safe_load(patched)

    args = cfg["users"][0]["user"]["exec"]["args"]
    assert "oidc-login" in args
    assert "get-token" in args
    assert any(
        a == "--oidc-issuer-url=https://k8s-val.eumetsat.europeanweather.cloud/dex"
        for a in args
    )
    assert any(a == "--oidc-client-id=kubermaticIssuer" for a in args)
    assert any(
        a == "--oidc-client-secret=buetTpb4Rnp0C5BgebuyGKS0CCXBtjFU" for a in args
    )
    assert "--oidc-extra-scope=email" in args
    assert "--oidc-extra-scope=groups" in args


def test_non_oidc_auth_provider_left_alone():
    raw = """
apiVersion: v1
kind: Config
users:
- name: token-user
  user:
    auth-provider:
      name: gcp
      config: {}
"""
    patched = patch_kubeconfig(raw)
    cfg = yaml.safe_load(patched)

    user = cfg["users"][0]["user"]
    assert "auth-provider" in user
    assert "exec" not in user


def test_user_without_auth_provider_unchanged():
    raw = """
apiVersion: v1
kind: Config
users:
- name: plain-user
  user:
    token: abc123
"""
    patched = patch_kubeconfig(raw)
    cfg = yaml.safe_load(patched)

    user = cfg["users"][0]["user"]
    assert user == {"token": "abc123"}


def test_extract_hostname():
    patched = patch_kubeconfig(_raw_kubeconfig())
    host = extract_hostname(patched)
    assert host == "abv9l8vmfm.kubermatic.k8s-val.eumetsat.europeanweather.cloud"


def test_extract_hostname_empty_on_no_clusters():
    assert extract_hostname("apiVersion: v1\nkind: Config\n") == ""
