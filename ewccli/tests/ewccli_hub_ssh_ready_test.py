#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Tests for the SSH readiness gate used before running Ansible."""

from unittest.mock import MagicMock

import pytest

from ewccli.commands.hub import hub_backends


@pytest.fixture
def no_sleep(monkeypatch):
    """Prevent any real sleeping during the tests."""
    monkeypatch.setattr(hub_backends.time, "sleep", lambda *_: None)


class FakeClock:
    """Monotonic clock that advances on every call."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def test_wait_for_ssh_ready_returns_true_when_port_accepts(monkeypatch, no_sleep):
    """A successful TCP connection means sshd is ready."""
    connect = MagicMock()
    monkeypatch.setattr(hub_backends.socket, "create_connection", connect)

    assert hub_backends.wait_for_ssh_ready("192.168.1.82") is True
    connect.assert_called_once()


def test_wait_for_ssh_ready_retries_until_ready(monkeypatch, no_sleep):
    """Connection errors are retried silently until sshd takes traffic."""
    attempts = {"count": 0}

    def fake_connect(address, timeout=None):  # noqa: ARG001
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise OSError("Connection timed out")
        return MagicMock()

    monkeypatch.setattr(hub_backends.socket, "create_connection", fake_connect)
    monkeypatch.setattr(hub_backends.time, "monotonic", FakeClock())

    assert hub_backends.wait_for_ssh_ready("192.168.1.82") is True
    assert attempts["count"] == 3


def test_wait_for_ssh_ready_times_out(monkeypatch, no_sleep):
    """A zero timeout fails immediately without probing."""
    connect = MagicMock()
    monkeypatch.setattr(hub_backends.socket, "create_connection", connect)

    assert (
        hub_backends.wait_for_ssh_ready("192.168.1.82", timeout_seconds=0) is False
    )
    connect.assert_not_called()


def test_wait_for_ssh_ready_without_ip_returns_false():
    """No IP address means there is nothing to probe."""
    assert hub_backends.wait_for_ssh_ready("") is False


def _run_ansible_item(
    monkeypatch, tmp_path, ssh_ready: bool
) -> tuple[int, MagicMock]:
    """Run run_ansible_item with ansible and SSH readiness stubbed out."""
    monkeypatch.setattr(
        hub_backends, "wait_for_ssh_ready", lambda *_, **__: ssh_ready
    )
    monkeypatch.setattr(
        hub_backends.ansible_backend, "install_ansible_roles", lambda **__: (0, "")
    )
    run_live = MagicMock(return_value=0)
    monkeypatch.setattr(hub_backends.ansible_backend, "run_ansible_live", run_live)
    monkeypatch.setattr(hub_backends.time, "sleep", lambda *_: None)

    return_code = hub_backends.run_ansible_item(
        item="ssh-bastion-flavour",
        item_inputs=None,
        server_name="ssh-bastion-flavour",
        ip_machine="192.168.1.82",
        username="cloud-user",
        main_file_path=str(tmp_path / "main.yml"),
        requirements_file_path=str(tmp_path / "requirements.yml"),
        working_directory_path=str(tmp_path),
        ssh_private_key_path=str(tmp_path / "key"),
    )
    return return_code, run_live


def test_run_ansible_aborts_when_ssh_never_ready(monkeypatch, tmp_path):
    """Ansible must not run when sshd never starts accepting traffic."""
    return_code, run_live = _run_ansible_item(monkeypatch, tmp_path, ssh_ready=False)

    assert return_code == 1
    run_live.assert_not_called()


def test_run_ansible_runs_when_ssh_ready(monkeypatch, tmp_path):
    """Ansible runs as soon as the SSH readiness gate passes."""
    return_code, run_live = _run_ansible_item(monkeypatch, tmp_path, ssh_ready=True)

    assert return_code == 0
    run_live.assert_called_once()


def test_run_ansible_item_dry_run_skips_ssh_wait(monkeypatch, tmp_path):
    """Dry runs must not probe the network."""
    wait = MagicMock()
    monkeypatch.setattr(hub_backends, "wait_for_ssh_ready", wait)

    return_code = hub_backends.run_ansible_item(
        item="ssh-bastion-flavour",
        item_inputs=None,
        server_name="ssh-bastion-flavour",
        ip_machine="192.168.1.82",
        username="cloud-user",
        main_file_path=str(tmp_path / "main.yml"),
        requirements_file_path=str(tmp_path / "requirements.yml"),
        working_directory_path=str(tmp_path),
        ssh_private_key_path=str(tmp_path / "key"),
        dry_run=True,
    )

    assert return_code == 0
    wait.assert_not_called()