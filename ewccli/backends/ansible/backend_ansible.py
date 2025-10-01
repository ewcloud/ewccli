#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Ansible backend methods."""

import os
import shutil
from typing import List, Optional

import ansible_runner

from ewccli.utils import run_command_from_host
from ewccli.logger import get_logger

_LOGGER = get_logger(__name__)


class AnsibleBackend:
    """Ansible backend class."""

    def run_ansible_live(
        self,
        working_directory_path: str,
        cmdline: List[str],
        description: Optional[str] = None,
        host: Optional[str] = None,
        env: Optional[dict] = None,
        extra_vars: Optional[str] = None,
    ):
        """
        Run an Ansible task (playbook or ad-hoc module) and stream output live.

        Parameters:
        - working_directory_path: Path to Ansible Runner's private_data_dir.
        - description: Optional description to log.
        - host: Host pattern for ad-hoc module run (optional).
        - env: Dictionary of environment variables (optional).
        - cmdline: command for ansible (optional)
        - extra_vars: --extra-vars equivalent

        Raises:
        - RuntimeError on failure.
        """
        _LOGGER.info(
            'Running: "%s" -> on host: "%s"',
            description or "Ansible task",
            host or "N/A",
        )

        def _handle_event(event):
            stdout = event.get("stdout")
            if stdout:
                _LOGGER.debug(stdout)
                pass

            if event.get("event") in ("runner_on_failed", "runner_on_unreachable"):
                msg = f"❌ Task '{description}' failed on host '{host}'"
                _LOGGER.error(msg)

        run_args = dict(
            private_data_dir=working_directory_path,
            envvars=env,
            cmdline=cmdline,
            extravars=extra_vars if extra_vars else None,
            # verbosity = 3,
            event_handler=_handle_event,
        )
        args_path = os.path.join(working_directory_path, "args")

        command = ""

        # if env:
        #     bash_env_line = " ".join(f"{k}={v}" for k, v in env.items())
        #     command += bash_env_line + " "

        command += " ".join(cmdline)

        if extra_vars:
            command += " --extra-vars " + "'" + extra_vars + "'"

        if not os.path.exists(args_path):
            with open(args_path, "w") as f:
                f.write(command)

        # json_mode=True if enabled print all logs.
        thread, runner = ansible_runner.run_async(json_mode=False, **run_args)

        # Wait for the background thread to finish
        thread.join()

        # Once done, remove the artifacts repository and env file
        if os.path.exists(args_path):
            os.remove(args_path)

        # artifacts keep all logs, remove it, but readd it if you want to debug
        for repo_name in ["env", "artifacts"]:
            repo_path = os.path.join(working_directory_path, repo_name)
            if os.path.exists(repo_path):
                _LOGGER.debug(f"Deleting folder: {repo_path}")
                shutil.rmtree(repo_path)
            else:
                _LOGGER.debug(f"Folder does not exist: {repo_path}")

        return runner.rc


    def run_ansible(
        self,
        description: str,
        command: List[str],
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        dry_run: bool = False,
    ) -> tuple[int, str]:
        """Run ansible command."""
        return_code, message = run_command_from_host(
            description=description,
            command=command,
            timeout=timeout,
            cwd=cwd,
            env=env,
            dry_run=dry_run,
        )

        return return_code, message

    def install_ansible_roles(self, requirements_path: str, dry_run: bool = False):
        """Install Ansible roles."""
        command = f"ansible-galaxy role install -r {requirements_path} --force"
        _LOGGER.info(f"Installing ansible roles from requirements: \n{command}\n")
        return_code, message = run_command_from_host(
            description="Install ansible roles",
            command=[command],
            timeout=None,
            # cwd=requirements_path,
            dry_run=dry_run,
        )

        return return_code, message
