#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

import os
from pathlib import Path

from ewccli.enums import Federee


class EWCCLIConfiguration:
    """EWC CLI global configuration."""

    EWC_CLI_NAME = "ewc"
    EWC_CLI_DEBUG_LEVEL = os.getenv("EWC_CLI_DEBUG_LEVEL", "INFO")
    EWC_CLI_DRY_RUN = bool(int(os.getenv("EWC_CLI_DRY_RUN", 0)))

    EWC_CLI_HUB_ITEMS_URL = "https://raw.githubusercontent.com/ewcloud/ewc-community-hub/refs/heads/main/items.yaml"
    EWC_CLI_HUB_DOWNLOAD_ITEMS = bool(int(os.getenv("EWC_CLI_HUB_DOWNLOAD_ITEMS", 0)))

    home_dir = Path.home()

    EWC_CLI_BASE_PATH = home_dir / ".ewccli"

    EWC_CLI_DEFAULT_TENANCY_NAME = "default-tenancy-name"
    EWC_CLI_DEFAULT_REGION = "default"
    EWC_CLI_DEFAULT_KEYPAIR_NAME = "ewc-hub-key"

    # EWC_CLI_HUB_ITEMS_PATH = files("ewccli.data").joinpath("items.yaml")
    EWC_CLI_HUB_ITEMS_PATH = EWC_CLI_BASE_PATH / "items.yaml"
    EWC_CLI_PRIVATE_SSH_KEY_PATH = home_dir / ".ssh/id_rsa"
    EWC_CLI_PUBLIC_SSH_KEY_PATH = home_dir / ".ssh/id_rsa.pub"

    EWC_CLI_DEFAULT_PATH_INPUTS = home_dir / ".ewccli/inputs"
    EWC_CLI_DEFAULT_PATH_OUTPUTS = home_dir / ".ewccli/outputs"

    # TODO: it needs to match EWC virtual image column
    # from https://confluence.ecmwf.int/display/EWCLOUDKB/EWC+Virtual+Images+Available
    EWC_CLI_IMAGES = {
        "ubuntu-22.04": "ubuntu-22.04-20250604054912",
        "ubuntu-24.04": "ubuntu-24.04-20250604102601",
        "rocky-8": "Rocky-8.10-20250604144456",
        "rocky-9": "Rocky-9.5-20250604142417",
    }

    EWC_CLI_DEFAULT_IMAGE = EWC_CLI_IMAGES["rocky-9"]

    EWC_CLI_IMAGES_USER = {
        "ubuntu-22.04": "ubuntu",
        "ubuntu-24.04": "ubuntu",
        "rocky-8": "cloud-user",
        "rocky-9": "cloud-user",
        EWC_CLI_IMAGES["ubuntu-22.04"]: "ubuntu",
        EWC_CLI_IMAGES["ubuntu-24.04"]: "ubuntu",
        EWC_CLI_IMAGES["rocky-8"]: "cloud-user",
        EWC_CLI_IMAGES["rocky-9"]: "cloud-user",
    }

    EWC_CLI_AUTH_URL_MAP = {
        "https://auth.os-api.cci1.ecmwf.int:443": Federee.ECMWF.value,
        "https://keystone.cloudferro.com:5000": Federee.EUMETSAT.value,
    }

    EWC_CLI_SITE_MAP = {
        Federee.ECMWF.value: "https://auth.os-api.cci1.ecmwf.int:443",
        Federee.EUMETSAT.value: "https://keystone.cloudferro.com:5000",
    }

    # GPU
    # TODO: it needs to match EWC virtual image column
    # from https://confluence.ecmwf.int/display/EWCLOUDKB/EWC+Virtual+Images+Available
    DEFAULT_IMAGES_GPU_MAP = {
        Federee.ECMWF.value: "Rocky-9.6-GPU-20250625141454",
        Federee.EUMETSAT.value: "Ubuntu 22.04 NVIDIA_AI",
    }

    EWC_CLI_GPU_IMAGES_USER = {
        Federee.ECMWF.value: "cloud-user",
        Federee.EUMETSAT.value: "eouser",
    }

    # Flavors

    # CPU
    # TODO: Create config list
    DEFAULT_CPU_FLAVOURS_MAP = {
        Federee.ECMWF.value: "4cpu-4gbmem-30gbdisk",
        Federee.EUMETSAT.value: "eo1.large",
    }

    # GPU
    # TODO: To be removed once the harmonization on flavours is finalized
    GPU_FLAVOURS_MAP = {
        Federee.ECMWF.value: [
            "2cpu-4gbmem-30gbdisk",
            "8cpu-64gbmem-30gbdisk-a100.2g.20gbgpu",
            "16cpu-128gbmem-30gbdisk-40gbgpu",
            "48cpu-384gbmem-30gbdisk-80gbgpu",
        ],
        Federee.EUMETSAT.value: [
            "vm.a6000.1",
            "vm.a6000.2",
            "vm.a6000.4",
            "vm.a6000.8",
        ],
    }

    DEFAULT_GPU_FLAVOURS_MAP = {
        Federee.ECMWF.value: "8cpu-64gbmem-30gbdisk-a100.1g.10gbgpu",
        Federee.EUMETSAT.value: "vm.a6000.2",
    }

    DEFAULT_NETWORK_MAP = {
        Federee.ECMWF.value: "private",
        Federee.EUMETSAT.value: "private",
    }

    DEFAULT_EXTERNAL_NETWORK_MAP = {
        Federee.ECMWF.value: "external-internet",
        Federee.EUMETSAT.value: "external",
    }

    DEFAULT_SECURITY_GROUP_MAP = {
        Federee.ECMWF.value: ("ssh",),
        Federee.EUMETSAT.value: ("ssh",),
    }

    # Crossplane configurations
    DEFAULT_KUBERNETES_SERVER = {
        Federee.ECMWF.value: "",
        Federee.EUMETSAT.value: "",
    }


config = EWCCLIConfiguration()
