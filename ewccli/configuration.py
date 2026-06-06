#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

import os
from pathlib import Path

from ewccli.enums import Federee, Region, FedereeDNSMapping


class EWCCLIConfiguration:
    """EWC CLI global configuration."""

    EWC_CLI_NAME = "ewc"
    EWC_CLI_DEBUG_LEVEL = os.getenv("EWC_CLI_DEBUG_LEVEL", "INFO")
    EWC_CLI_DRY_RUN = bool(int(os.getenv("EWC_CLI_DRY_RUN", 0)))

    EWC_CLI_HUB_ITEMS_URL = "https://raw.githubusercontent.com/ewcloud/ewc-community-hub/refs/heads/main/items.yaml"
    EWC_CLI_HUB_DOWNLOAD_ITEMS = bool(int(os.getenv("EWC_CLI_HUB_DOWNLOAD_ITEMS", 0)))

    home_dir = Path.home()

    EWC_CLI_BASE_PATH = home_dir / ".ewccli"

    EWC_CLI_PROFILES_PATH = EWC_CLI_BASE_PATH / "profiles"

    EWC_CLI_DEFAULT_PROFILE_NAME = "default"
    EWC_CLI_DEFAULT_FEDEREE = "default"
    EWC_CLI_DEFAULT_KEYPAIR_NAME = "ewc-hub-key"

    # EWC_CLI_HUB_ITEMS_PATH = files("ewccli.data").joinpath("items.yaml")
    EWC_CLI_HUB_ITEMS_PATH = EWC_CLI_BASE_PATH / "items.yaml"
    EWC_CLI_HUB_SSH_REPO_PATH = EWC_CLI_BASE_PATH / ".ssh"
    EWC_CLI_PRIVATE_SSH_KEY_PATH = EWC_CLI_HUB_SSH_REPO_PATH / "id_rsa"
    EWC_CLI_PUBLIC_SSH_KEY_PATH = EWC_CLI_HUB_SSH_REPO_PATH / "id_rsa.pub"

    EWC_CLI_DEFAULT_PATH_INPUTS = EWC_CLI_BASE_PATH / "inputs"
    EWC_CLI_DEFAULT_PATH_OUTPUTS = EWC_CLI_BASE_PATH / "outputs"

    # CPU images
    EWC_CLI_CPU_IMAGES = [
        "Rocky-8",
        "Rocky-9",
        "Ubuntu-22.04",
        "Ubuntu-24.04",
    ]

    EWC_CLI_DEFAULT_IMAGE = "Rocky-9"

    EWC_CLI_IMAGES_USER = {
        "Ubuntu-22.04": "ubuntu",
        "Ubuntu-24.04": "ubuntu",
        "Rocky-8": "cloud-user",
        "Rocky-9": "cloud-user",
        "Rocky-9-GPU": "cloud-user",
        "Ubuntu 22.04 NVIDIA_AI": "eouser",
        "Ubuntu 24.04 NV_GRID_Open": "eouser",
    }

    EWC_CLI_SITE_MAP = {
        Federee.ECMWF.value: {
            Region.CC1.value: "https://auth.os-api.cci1.ecmwf.int:443",
            Region.CC2.value: "https://auth.os-api.cci2.ecmwf.int:443",
        },
        Federee.EUMETSAT.value: {
            Region.WAW31.value: "https://keystone.cloudferro.com:5000",
            Region.R1.value: "https://keystone.api.r1.cloud.eumetsat.int",
            Region.R2.value: "https://keystone.api.r2.cloud.eumetsat.int"
        },
    }

    EWC_CLI_AUTH_URL_MAP: dict[str, Federee] = {
        url: federee
        for federee, regions in EWC_CLI_SITE_MAP.items()
        for url in regions.values()
    }

    def allowed_regions(self, federee: Federee) -> list[str]:
        return [region for region in self.EWC_CLI_SITE_MAP[federee].keys()]

    # GPU images short custom names
    EWC_CLI_GPU_IMAGES_SITE_MAP: dict[Federee, dict[Region, str]] = {
        Federee.ECMWF.value: {
            Region.CC1.value: "Rocky-9-GPU",
            Region.CC2.value: "Rocky-9-GPU",
        },
        Federee.EUMETSAT.value: {
            Region.WAW31.value: "Ubuntu-22.04-GPU",
            Region.R1.value: "Ubuntu-24.04-GPU",
            Region.R2.value: "Ubuntu-24.04-GPU",
        }
    }

    # GPU images
    EWC_CLI_GPU_IMAGES = [
        gpu_image
        for regions in EWC_CLI_GPU_IMAGES_SITE_MAP.values()
        for gpu_image in regions.values()
    ]

    # Openstack value of the GPU images
    EWC_CLI_OS_GPU_IMAGES_SITE_MAP: dict[Federee, dict[Region, str]] = {
        Federee.ECMWF.value: {
            Region.CC1.value: "Rocky-9.6-GPU",  # This can be find after normalization
            Region.CC2.value: "Rocky-9.6-GPU",  # This can be find after normalization
        },
        Federee.EUMETSAT.value: {
            Region.WAW31.value: "Ubuntu 22.04 NVIDIA_AI",  # ( usually fixed)
            Region.R1.value: "Ubuntu 24.04 NV_GRID_Open",  # ( usually fixed)
            Region.R2.value: "Ubuntu 24.04 NV_GRID_Open",  # ( usually fixed)
        },
    }

    # Flavors

    # CPU
    DEFAULT_CPU_FLAVOURS_MAP: dict[Federee, dict[Region, str]] = {
        Federee.ECMWF.value: {
            Region.CC1.value: "4cpu-4gbmem-30gbdisk",
            Region.CC2.value: "4cpu-4gbmem-30gbdisk",
        },
        Federee.EUMETSAT.value: {
            Region.WAW31.value: "eo1.large",
            Region.R1.value: "4cpu-4gbmem",
            Region.R2.value: "4cpu-4gbmem",
        },
    }
    # GPU
    GPU_FLAVOURS_MAP: dict[Federee, dict[Region, list[str]]] = {
        Federee.ECMWF.value: {
            Region.CC1.value: [
                "8cpu-64gbmem-30gbdisk-a100.1g.10gbgpu",
                "8cpu-64gbmem-30gbdisk-a100.2g.20gbgpu",
                "16cpu-128gbmem-30gbdisk-40gbgpu",
            ],
            Region.CC2.value: [
                "8cpu-64gbmem-30gbdisk-a100.1g.10gbgpu",
                "8cpu-64gbmem-30gbdisk-a100.2g.20gbgpu",
                "16cpu-128gbmem-30gbdisk-40gbgpu",
            ],
        },

        Federee.EUMETSAT.value: {
            Region.WAW31.value: [
                "vm.a6000.1",
                "vm.a6000.2",
                "vm.a6000.4",
                "vm.a6000.8",
            ],
            Region.R1.value: [
                "6cpu-32gbmem-h200.1g.18gb",
                "11cpu-64gbmem-h200.2g.35gb",
                "17cpu-128gbmem-h200.3g.71gb",
            ],
            Region.R2.value: [
                "6cpu-32gbmem-h200.1g.18gb",
                "11cpu-64gbmem-h200.2g.35gb",
                "17cpu-128gbmem-h200.3g.71gb",
            ],
        },
    }

    DEFAULT_GPU_FLAVOURS_MAP: dict[Federee, dict[Region, str]] = {
        Federee.ECMWF.value: {
            Region.CC1.value: "8cpu-64gbmem-30gbdisk-a100.1g.10gbgpu",
            Region.CC2.value: "8cpu-64gbmem-30gbdisk-a100.1g.10gbgpu",
        },

        Federee.EUMETSAT.value: {
            Region.WAW31.value: "vm.a6000.2",
            Region.R1.value: "6cpu-32gbmem-h200.1g.18gb",
            Region.R2.value: "6cpu-32gbmem-h200.1g.18gb",
        },
    }

    # Network
    
    DEFAULT_NETWORK_MAP = {
        Federee.ECMWF.value: "private",
        Federee.EUMETSAT.value: "private",
    }

    DEFAULT_EXTERNAL_NETWORK_MAP = {
        Federee.ECMWF.value: "external-internet",
        Federee.EUMETSAT.value: "external",
    }

    DNS_CHECK_TIMEOUT_MINUTES = 20
    FEDEREE_DNS_MAPPING = {
        Federee.ECMWF.value: FedereeDNSMapping.ECMWF.value,
        Federee.EUMETSAT.value: FedereeDNSMapping.EUMETSAT.value,
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
