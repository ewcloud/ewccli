<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/othneildrew/Best-README-Template">
    <img src="https://raw.githubusercontent.com/ewcloud/ewc-community-hub/refs/heads/main/logos/EWCLogo.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">ewccli</h3>

  <p align="center">
    European Weather Cloud Command Line Interface
    <br />
    <a href="https://confluence.ecmwf.int/x/u0XOIQ#CommunityHubToolingDeployingviaewccli-VideoDemo">View Usage Demo</a>
    &middot;
    <a href="https://github.com/ewcloud/ewccli/issues">Report Bugs</a>
    &middot;
    <a href="https://github.com/ewcloud/ewccli/issues">Request Features</a>
    &middot;
    <a href="mailto:support@europeanweather.cloud">Get Support</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#introduction">Introduction</a></li>
    <li><a href="#prerequisties">Prerequisites</a>
      <ul>
        <li><a href="#openstack-inputs">Openstack Inputs</a></li>
      </ul>
    </li>
    <li><a href="#installing">Installing</a></li>
      <ul>
        <li><a href="#installing-with-pip-from-pypi">Installing with PIP from PyPI</a></li>
        <li><a href="#installing-from-source">Installing from source</a></li>
        <li><a href="#installing-in-a-container">Installing in a container</a></li>
      </ul>
    <li><a href="#getting-started">Getting started</a></li>
    <li><a href="#login-to-prepare-the-environment">Login to prepare the environment</a></li>
    <li><a href="#list-items-in-the-catalog">List Items in the catalog</a></li>
    <li><a href="#deploy-items-from-the-catalog">Deploy Items from the catalog</a></li>
    <li><a href="#test-items-unreleased-or-from-private-sources">Test Items unreleased or from private sources</a></li>
      <ul>
        <li><a href="#preparing-a-test">Preparing a test</a></li>
        <li><a href="#running-a-test">Running a test</a></li>
      </ul>
    <li><a href="#Backends">Deploy a custom Item</a></li>
      <ul>
        <li><a href="#Openstack">Openstack</a></li>
        <li><a href="#Ansible">Ansible</a></li>
        <li><a href="#Terraform">Terraform</a></li>
        <li><a href="#Kubernetes">Kubernetes</a></li>
      </ul>
    <li><a href="#sw-bill-of-materials-(sbom)">SW Bill of Materials</a></li>
      <ul>
        <li><a href="#dependencies">Dependencies</a></li>
        <li><a href="#build/edit/test-dependencies">Build/Edit/Test Dependencies</a></li>
      </ul>
    <li><a href="#changelog">Changelog</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#development">Development</a></li>
    <li><a href="#code-styling">Code Styling</a></li>
      <ul>
        <li><a href="#resolving-style-issues">Resolving Style Issues</a></li>
      </ul>
    <li><a href="#code-unittesting">Code Unittesting</a></li>
    <li><a href="#coverage-reporting">Coverage Reporting</a></li>
    <li><a href="#documenting">Documenting</a></li>
    <li><a href="#copyright-and-license">Copyright and License</a></li>
    <li><a href="#authors">Authors</a></li>
  </ol>
</details>

## Introduction

The `ewccli` is the European Weather Cloud (EWC) Command Line Interface (CLI). This tool is developed to support EWC users on the use of the EWC services.


## Prerequisites

- You will need a python environment to run the library implementation of this code. Python version **3.11** or higher.
- **git** installed on your operating system. (usually is available to most OS nowadays)

### Openstack inputs

You can use the following [link](https://confluence.ecmwf.int/display/EWCLOUDKB/EWC+-+How+to+request+Openstack+Application+Credentials) to obtain:
- Applications Credentials (ID and secret)

## Installing

We recommend installing **ewccli** inside a **virtual environment** to avoid dependency conflicts with system packages.

### Installing with PIP from PyPI

The EWC CLI Python package is available through [PyPI](https://pypi.org/):

```bash
pip install ewccli
```

### Installing from source

1. Clone this repository and move into it
```bash
git clone THIS_REPO && cd ewccli
```

2. Create virtualenv with minimum python version > 3.10

```bash
python3 -m venv ewcclienv
```

3. Activate the virtual environment

```bash
source ./ewcclienv/bin/activate
```

4. Upgrade pip

```bash
pip install --upgrade pip
```

5. Install the package

```bash
pip install -e .
```

### Installing in a container
> If [Docker](https://www.docker.com/) is your preferred containerization tool, you can replace `podman` with `docker` in the commands below.

You may also run in an completely isolated environment using containerization. After cloning the repository and `cd` into it.

1. Clone this repository and move into it
```bash
git clone THIS_REPO && cd ewccli
```

2. Create a wheel package (`./dist/ewccli-<version>-py3-none-any.whl`)

```bash
pip install -q build
```

```bash
python3 -m build
```

3. Build an image including the package previously created

```bash
podman build --no-cache -t ewccli -f ./Containerfile .
```

4. Start a container with an interactive shell

```bash
podman run -it --rm  --workdir /home/ewccli --entrypoint /bin/bash ewccli
```

## Getting started

Then run `ewc` to verify everything works:

![ewccli-default](https://raw.githubusercontent.com/ewcloud/ewccli/main/images/ewccli-default.png)

If you get a WARNING like `WARNING: The script ewc is installed in '~/.local/bin' which is not on PATH.` Add the following to your profile configuration file:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
```

## Login to prepare the environment

```bash
ewc login
```

IMPORTANT:

- EWC CLI uses the following order of importance:
    - env variables
    - cli config
    - any other config (e.g. Openstack cloud.yaml or Kubernetes `kubeconfig` file)

All your profiles are saved under `~/.ewccli/profiles`

You can manually add profiles in the same file and the ewccli can use them already.

Info required for a profile:
```
[my-profile]
federee = EUMETSAT or ECMWF
tenant_name = eumetsat-ewc-communityhub
application_credential_id = 
application_credential_secret = 
ssh_public_key_path =
ssh_private_key_path =
```

## List Items in the catalog

The following command shows the current available Items. Official Items are listed [here](https://github.com/ewcloud/ewc-community-hub/blob/main/items.yaml).

```bash
ewc hub list
```
![ewccli-hub-list](https://raw.githubusercontent.com/ewcloud/ewccli/main/images/ewccli-hub-list.png)


## Deploy Items from the catalog

![ewccli-hub-deploy](https://raw.githubusercontent.com/ewcloud/ewccli/main/images/ewccli-hub-deploy.png)

```bash
ewc hub deploy ITEM
```
where ITEM is taken from `ewc hub list` command under Item column.

## Test Items unreleased or from private sources

If you would like to test the deployment of:
* **an Item with private source code (local or remote)**
  
  OR
* **a new Item, not yet published in the EWC Community Hub**

  OR

* **a new version of an Item, not yet updated in the EWC Community Hub**

you can take advantage of the `--path-to-catalog` to point the EWCCLI to the correct source location, and deploy the Item to your target tenant of choice.

### Preparing a test
Create a local catalogue file, named `./custom_catalog.yaml`, with the complete metadata for your Item:

>⚠️ Always verify the latest Items metadata schema directly from the [EWC Hub Catalogue documentation](https://github.com/ewcloud/ewc-community-hub?tab=readme-ov-file#items-metadata).

```yaml
apiVersion: communityhub.europeanweather.cloud/v1alpha1
kind: CommunityHubCatalog
spec:
  Items:
    my-test-item:
      name: "my-test-item"
      version: "0.0.1"
      description: |
        My first Item in EWC Community Hub

      ewccli:
        pathToRequirementsFile: path_to_your_requirements_file
        pathToMainFile: path_to_your_main_ansible_playbook_file
        publicIP: true
        inputs:
          - name: myoptionalinput
            description: "myoptionalinput"
            type: str
            default: Add default key if you want this input to be optional. If this key is not set, the ewccli will expect this value to be provided by the user (mandatory input)
          - name: mymandatoryinput
            description: "mymandatoryinput: cli will complain if this is not provided as --item-inputs"
            type: str
      home: https://github.com/your-repo
      sources:
        - https://github.com/your-repo.git OR /home/murdaca/custom-items/new-item
      maintainers:
        - name: your name or your org
          email: youremail
          url: https://github.com/your-repo/issues
      icon: https://raw.githubusercontent.com/ewcloud/ewc-community-hub/refs/heads/main/logos/EWCLogo.png
      annotations:
        technology: "Ansible Playbook"
        category: "Test Item"
        supportLevel: "Community"
        licenseType: "Apache License 2.0"
        others: "Deployable,EWCCLI-compatible"
      displayName: My First EWC Community hub Item
      summary: My test Item
      license: https://github.com/your-repo/blob/main/LICENSE
      published: true
```

where 

- `sources` can be (only the first element in the list is considered):
    - Public repo URL (e.g. https://github.com/your-repo.git) if your repository is public already
    - Absolute path to a directory with the Item (e.g. `/home/murdaca/custom-items/new-item`). The path needs to point to a directory that needs to exists an not be empty. (WARNING: No local path are accepted!)
- `pathToMainFile` is the relattive path to your directory or repository
- `pathToRequirementsFile` is the relattive path to your directory or repository
- `publicIP` is a flag used to enable deployment of 
- `ewccli.inputs` is the list of inputs you want the user to be able to provide, they can be mandatory or optional, respecively with default key not set or set.

### Running a test
Once metadata is correct and complete, execute `list`, `show` or `deploy` commands as needed:

```bash
ewc hub --path-to-catalog ./custom_catalog.yaml list|show|deploy
```
```bash
ewc hub --path-to-catalog ./custom_catalog.yaml show
```
```bash
ewc hub --path-to-catalog ./custom_catalog.yaml deploy
```

## Backends

This section described the backends used and which commands are backed by those backends.

### Openstack

Used by infra and hub subcommands.

### Ansible

Used by hub subcommand.

### Terraform

Used by hub subcommand. (COMING SOON)

### Kubernetes

Used by dns, s3, k8s subcommmands. (COMING SOON)

## SW Bill of Materials (SBoM)

### Dependencies
The following dependencies are not included in the package but they are required and will be downloaded at build or compilation time:

| Dependency | Version | License | Home URL |
|------|---------|---------|--------------|
| requests | 2.32.5 | Apache Software License (Apache-2.0) | https://requests.readthedocs.io/en/latest |
| click | 8.1.8 | BSD-3-Clause | https://github.com/pallets/click |
| rich | 14.1.0 | MIT License | https://github.com/Textualize/rich |
| rich-click | 1.8.9 | MIT License | https://pypi.org/project/rich-click |
| prompt_toolkit | 3.0.51 | BSD-3-Clause License | https://python-prompt-toolkit.readthedocs.io/en/stable |
| pyyaml | 6.0.2 | MIT License | https://pyyaml.org |
| cryptography | 45.0.6 | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography |
| python-openstackclient | 8.2.0 | Apache Software License (Apache-2.0) | https://docs.openstack.org/python-openstackclient/latest |
| ansible | 11.10.0 | GNU General Public License v3 or later (GPLv3+) (GPL-3.0-or-later) | https://www.redhat.com/en/ansible-collaborative |
| ansible-runner | 2.4.1 | Apache Software License (Apache Software License, Version 2.0) | https://ansible.readthedocs.io/projects/runner/en/latest |
| kubernetes | 33.1.0 | Apache Software License (Apache License Version 2.0) | https://github.com/kubernetes-client/python |
| pydantic | 2.12.5 | MIT License | https://github.com/pydantic/pydantic |


### Build/Edit/Test Dependencies
The following dependencies are only required for building/editing/testing the software:

| Dependency | Version | License | Home URL |
|------|---------|---------|--------------|
| pytest | 8.4.1  | MIT License (MIT) | https://docs.pytest.org/en/latest |
| pytest-html | 4.1.1 | MIT License (MIT)   | https://github.com/pytest-dev/pytest-html  |
| pytest-mock | 3.14.1  | MIT License (MIT) | https://github.com/pytest-dev/pytest-mock |
| coverage | 7.10.5  | Apache Software License (Apache License Version 2.0) | https://github.com/nedbat/coveragepy |
| pre-commit | 4.3.0  | MIT License (MIT) | https://github.com/pre-commit/pre-commit  |
| sphinx | 8.1.3  | BSD-2-Clause License | https://www.sphinx-doc.org/en/master |
| sphinx-click | 6.0.0  | MIT License (MIT) | https://github.com/click-contrib/sphinx-click |
| sphinx-rtd-theme | 3.0.2  | MIT License (MIT) | https://sphinx-rtd-theme.readthedocs.io/en/stable |
| pydeps | 3.0.1  | BSD-2-Clause License | https://github.com/thebjorn/pydeps  |

## Changelog
All notable changes (i.e. fixes, features and breaking changes) are documented
in the [CHANGELOG.md](./CHANGELOG.md).

## Contributing
Thanks for taking the time to join our community and start contributing!

Please make sure to:

- Familiarize yourself with our Code of Conduct before
contributing.

- See CONTRIBUTING.md for instructions on how to request
or submit changes.

## Development

1. Fork this repository and move into it
```bash
git clone https://github.com/ewcloud/ewccli.git && cd ewccli
```

2. Install the package for testing
```bash
pip install --user -e .[test]
```

3. Modify the local code and test changes.

4. Push code to your fork and open a pull request.

## Code Styling
Execute all linting tests by running:

```bash
pre-commit run --all-files
```
This will provide you with hints about:
* Basic format of the files (i.e. spacing, line breaking, etc.) using `black`
* [PEP](https://peps.python.org/) standars infringement flagged by `flake8`
* Static typing and type hinting recommendations given by `mypy`

### Resolving Style Issues

To enforce basic formating issues , run:
```bash
black ./
```

Currently, there is no automated way of addressing errors raised by `flake8` and `mypy`.
To resolve those, check the logs from the `pre-commit` execution, understand the type of error and adjust the code accordingly.

## Code Unittesting

Execute all tests by running:

```bash
pytest
```

### Coverage Reporting

Generate unittest coverage reports in standard formats by executing:

```bash
coverage run --module pytest --no-header --verbose -ra --junitxml=coverage.xml --html=coverage.html
```

## Documenting
Generate documentation from source code docstrings:

```bash
sphinx-build -b html docs/source/ Documentation/
```

## Copyright and License
Copyright © EUMETSAT, ECMWF 2026

The provided code and instructions are licensed under [GPLv3+](./LICENSE).
They are intended to automate the setup of an environment that includes
third-party software components.
The usage and distribution terms of the resulting environment are
subject to the individual licenses of those third-party libraries.

Users are responsible for reviewing and complying with the licenses of
all third-party components included in the environment.

Contact [EUMETSAT](http://www.eumetsat.int) for details on the usage and distribution terms.

## Authors
* [**Francesco Murdaca**](mailto:francesco.murdaca@eumetsat.int) - *Initial work and maintainer* - [EUMETSAT](http://www.eumetsat.int)
