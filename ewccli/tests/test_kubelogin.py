"""Tests for the kubelogin subprocess wrapper."""

import json
import pytest
from unittest.mock import patch, MagicMock

from ewccli.backends.kkp.kubelogin import get_kkp_token


def _exec_credential(token="my-kkp-token"):
    return json.dumps({"status": {"token": token}})


@patch("ewccli.backends.kkp.kubelogin.subprocess.run")
def test_get_token_success_parses_exec_credential(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = _exec_credential("kkp-token-xyz")
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    token = get_kkp_token(
        issuer="https://k8s-val.example.com/dex",
        client_id="kubermatic",
        client_secret="secret123",
    )

    assert token == "kkp-token-xyz"

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert cmd[0] == "kubelogin"
    assert "get-token" in cmd
    assert "--oidc-issuer-url=https://k8s-val.example.com/dex" in cmd
    assert "--oidc-client-id=kubermatic" in cmd
    assert "--oidc-client-secret=secret123" in cmd
    assert "--oidc-extra-scope=email" in cmd
    assert "--oidc-extra-scope=groups" in cmd
    assert "--skip-open-browser" in cmd
    assert call_args[1]["capture_output"] is True
    assert call_args[1]["text"] is True


@patch("ewccli.backends.kkp.kubelogin.subprocess.run")
def test_get_token_failure_raises_runtime_error(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error: something went wrong"
    mock_run.return_value = mock_result

    with pytest.raises(RuntimeError, match="kubelogin failed"):
        get_kkp_token("iss", "cid", "secret")


@patch("ewccli.backends.kkp.kubelogin.subprocess.run")
def test_get_token_invalid_json_raises_runtime_error(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "not json at all"
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    with pytest.raises(RuntimeError, match="invalid ExecCredential"):
        get_kkp_token("iss", "cid", "secret")


@patch("ewccli.backends.kkp.kubelogin.subprocess.run")
def test_get_token_missing_status_token_raises(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps({"status": {}})
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    with pytest.raises(RuntimeError, match="invalid ExecCredential"):
        get_kkp_token("iss", "cid", "secret")
