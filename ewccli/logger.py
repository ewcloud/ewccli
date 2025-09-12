#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""EWC CLI Logger."""

import logging
from datetime import datetime, timezone
from rich.console import Console
from rich.logging import RichHandler
from ewccli.configuration import config as ewc_hub_config


# Optionally use rich Console globally
console = Console()


class UTCFormatter(logging.Formatter):
    """UTCFormatter for logging."""

    def format_time(self, record, datefmt=None):
        """Format time."""
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            s = dt.strftime(datefmt)
        else:
            # Default format with UTC indication
            s = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        return s


def get_logger(name=None):
    """Create logger"""
    logger = logging.getLogger(name)

    if not logger.hasHandlers():  # Avoid adding handlers multiple times
        # Set log level from config
        level = logging.INFO
        if getattr(ewc_hub_config, "EWC_CLI_DEBUG_LEVEL", "").upper() == "DEBUG":
            level = logging.DEBUG

        elif getattr(ewc_hub_config, "EWC_CLI_DEBUG_LEVEL", "").upper() == "INFO":
            level = logging.INFO

        logger.setLevel(level)

        handler = RichHandler(
            show_time=True,
            show_level=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True,  # Enables rich markup like [bold red] etc.
            console=console,
        )
        # formatter = UTCFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        # handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.propagate = False  # Prevent double logging if root logger also logs

    return logger
