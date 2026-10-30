#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2026 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

"""Tests for EWC Hub backends (git_clone_item ref checkout)."""

import subprocess

from pathlib import Path

import pytest

import ewccli.commands.hub.hub_backends as hub_backends
from ewccli.commands.hub.hub_backends import git_clone_item


@pytest.fixture
def local_repo(tmp_path):
    """Create a local git repo with a tag and a later commit on main.

    Layout:
        tag 1.0.0 -> f.txt contains "v1"
        HEAD (main) -> f.txt contains "v2-later-commit"
    """
    repo = tmp_path / "itemrepo"
    repo.mkdir()

    def sh(cmd: str) -> None:
        result = subprocess.run(
            cmd, shell=True, cwd=repo, capture_output=True, text=True
        )
        assert result.returncode == 0, f"{cmd} failed: {result.stderr}"

    sh("git init -q -b main .")
    sh("git config user.email test@example.com")
    sh("git config user.name test")

    (repo / "f.txt").write_text("v1")
    sh("git add .")
    sh('git commit -qm "v1"')
    sh("git tag 1.0.0")

    (repo / "f.txt").write_text("v2-later-commit")
    sh("git add .")
    sh('git commit -qm "v2"')

    return repo


@pytest.fixture(autouse=True)
def skip_http_accessibility_check(monkeypatch):
    """The accessibility check performs an HTTP GET; not applicable to local repos."""
    monkeypatch.setattr(hub_backends, "check_github_repo_accessible", lambda s: True)


def _content(out_dir: Path) -> str:
    return (out_dir / "itemrepo" / "f.txt").read_text()


def test_fresh_clone_checks_out_ref(local_repo, tmp_path):
    """A fresh clone must be checked out at the requested ref, not HEAD."""
    out = tmp_path / "out"

    rc, msg = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        ref="1.0.0",
    )

    assert rc == 0, msg
    assert _content(out) == "v1"


def test_existing_clone_still_checks_out_ref(local_repo, tmp_path):
    """Even when the clone is skipped, the repo must be brought to the ref.

    This is the core of the issue: without --force the clone is skipped, but
    different users deploying the same item version must run the same code.
    """
    out = tmp_path / "out"

    # First run: clone at ref
    rc, _ = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        ref="1.0.0",
    )
    assert rc == 0

    # Simulate new commits landing on main after the clone.
    # The clone does not inherit the source repo's local git config, and CI
    # runners may have no global identity, so pass it inline.
    repo = out / "itemrepo"
    (repo / "f.txt").write_text("v3-even-later")
    subprocess.run(
        "git add . && git -c user.email=test@example.com"
        " -c user.name=test commit -qm 'v3'",
        shell=True,
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )

    # Second run without force: clone is skipped, but ref is re-checked-out
    rc, msg = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        ref="1.0.0",
    )

    assert rc == 0, msg
    assert _content(out) == "v1"


def test_unknown_ref_fails_with_clear_message(local_repo, tmp_path):
    """A ref that matches no tag/branch/commit must fail with a clear error."""
    out = tmp_path / "out"

    rc, msg = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        ref="9.9.9",
    )

    assert rc != 0
    assert "9.9.9" in msg
    assert "tag, branch or commit" in msg


def test_no_ref_keeps_previous_behaviour(local_repo, tmp_path):
    """Without a ref, the function only clones (backwards compatible)."""
    out = tmp_path / "out"

    rc, _ = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
    )

    assert rc == 0
    # HEAD of main is the latest commit
    assert _content(out) == "v2-later-commit"


def test_force_reclones_and_checks_out_ref(local_repo, tmp_path):
    """--force deletes the clone, re-clones and still checks out the ref."""
    out = tmp_path / "out"

    rc, _ = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        ref="1.0.0",
    )
    assert rc == 0

    rc, msg = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        force=True,
        ref="1.0.0",
    )

    assert rc == 0, msg
    assert _content(out) == "v1"


def test_force_on_missing_clone_does_not_crash(local_repo, tmp_path):
    """--force with no existing clone must not raise (rmtree guard)."""
    out = tmp_path / "out"

    rc, msg = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        force=True,
        ref="1.0.0",
    )

    assert rc == 0, msg
    assert _content(out) == "v1"


def test_dry_run_skips_everything(local_repo, tmp_path):
    """Dry run must not clone or checkout."""
    out = tmp_path / "out"

    rc, msg = git_clone_item(
        source=f"file://{local_repo}",
        repo_name="itemrepo",
        command_path=str(out),
        dry_run=True,
        ref="1.0.0",
    )

    assert rc == 0
    assert "Dry run" in msg
    assert not (out / "itemrepo").exists()