# ewccli

`ewccli` is the European Weather Cloud (EWC) Command Line Interface (CLI). This tool is developed to support EWC users on the use of the EWC services.

For more info about this SW, you may contact the [European Weather Cloud](http://support.europeanweather.cloud/)
<[support@europeanweather.cloud](mailto:support@europeanweather.cloud)>.

## Copyright and License
Copyright © EUMETSAT, ECMWF 2025.

The provided code and instructions are licensed under [GPLv3+](./LICENSE).
They are intended to automate the setup of an environment that includes
third-party software components.
The usage and distribution terms of the resulting environment are
subject to the individual licenses of those third-party libraries.

Users are responsible for reviewing and complying with the licenses of
all third-party components included in the environment.

Contact [EUMETSAT](http://www.eumetsat.int) for details on the usage and distribution terms.

## Authors
* [**Francesco Murdaca**](mailto:francesco.murdaca@eumetsat.int) - *Initial work* - [EUMETSAT](http://www.eumetsat.int)

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

1. Fork this repository and move into it
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

## List items

The following command shows the current available items. Official items are listed [here](https://github.com/ewcloud/ewc-community-hub/blob/main/items.yaml).

```bash
ewc hub list
```
![ewccli-hub-list](https://raw.githubusercontent.com/ewcloud/ewccli/main/images/ewccli-hub-list.png)


## Deploy an item

![ewccli-hub-deploy](https://raw.githubusercontent.com/ewcloud/ewccli/main/images/ewccli-hub-deploy.png)

```bash
ewc hub deploy ITEM
```
where ITEM is taken from `ewc hub list` command under Item column.

## Deploy a custom item

If you want to test the deployment of a new item, not yet published to EWC Community Hub, you can use the `--path-to-catalog` flag available. 

For example you can create the following file `custom_item.yaml` with the following Ansible Playbook item:

```yaml
apiVersion: communityhub.europeanweather.cloud/v1alpha1
kind: CommunityHubCatalog
spec:
  items:
    my-test-item:
      name: "my-test-item"
      version: "0.0.1"
      description: |
        My first item in EWC Community Hub

      ewccli:
        pathToMainFile: path_to_your_main_ansible_playbook_file
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
        category: "Machine Learning & AI, GPU-accelerated"
        supportLevel: "Community"
        licenseType: "Apache License 2.0"
        others: "Deployable,EWCCLI-compatible"
      displayName: My First EWC Community hub item
      summary: My test item
      license: https://github.com/your-repo/blob/main/LICENSE
      published: true
```

where `sources` can be (only the first element in the list is considered):

    - Public repo URL (e.g. https://github.com/your-repo.git) if your repository is public already
    - Absolute path to a directory with the item (e.g. /home/murdaca/custom-items/new-item). The path needs to point to a directory that needs to exists an not be empty. (WARNING: No local path are accepted!)

Once ready you can try the following commands:

```bash
ewc hub --path-to-catalog PATH-TO-CATALOG list|show|deploy
```
where PATH-TO-CATALOG is by default the official published catalog available [here](https://github.com/ewcloud/ewc-community-hub/blob/main/items.yaml).

list|show|deploy commands work the same, but they will rely on a custom catalogue file.

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
| pydantic | 2.11.7  | MIT License (MIT) | https://github.com/pydantic/pydantic  |

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

4. When you are happy, push code to your fork and open a MR (Gitlab) or PR (Github)


## Generate docs

```bash
sphinx-build -b html docs/source/ Documentation/
```

## Check coverage

```bash
coverage run -m pytest
```

## Run tests

```bash
pytest
```

## Test in a container

After cloning the repository and cd into it.

1. Create the .dist/ repo
```bash
pip install -q build
```

```bash
python3 -m build
```


2. Create a container if you need to test anything before.

```bash
podman build -t test-ewccli -f ./Containerfile .
```
or same command with `docker` if you use it.
