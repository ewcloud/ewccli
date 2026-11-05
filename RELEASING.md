# Releasing ewccli

## Before you begin

### 1. Trigger the CI to update of CHANGELOG.md and git tags
> 💡 The CI only makes changes only if new [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) of type `feat` and `fix` added to the main branch since the last `git tag` was created.

Ensure that all pull requests relevant for the next release have been merged before triggering the [Semantic Release GitHub Action](https://github.com/ewcloud/ewccli/actions/workflows/release.yml).


After CI completion, verify a new tag (in semantic version format `x.y.z`) is created on the main branch, and the [CHANGELOG.md](./CHANGELOG.md) reflects the relevant features/fixes as they appear in the commit history.

### 2. Pull the latest code chances
Make sure to pull the latest code and checkout the correct tag (in semantic version format `x.y.z`):

```bash
git checkout main
```

```bash
git pull
```

```bash
git checkout  x.y.z
```

## Release on PyPI (only admins with PyPI keys)

### 1. Build package

To build the package and generate the distribution, use PyPA build.

#### 1.1. Install the build tool
```bash
pip install -q build
```

```bash
python3 -m build
```

you will end up with a `/dist` file. The .whl file and .tar.gz can then be distributed and installed or pushed to PyPI.

### 2. Push package to TestPyPI

#### 2.1. Install twine
```bash
pip install twine
```

If you want to test first, use TestPyPI:
```bash
twine upload --repository testpypi dist/*
```

You'll be prompted for your TestPyPI username & password.

Once done check on [TestPyPI](https://test.pypi.org/).

### 3. Push package to PyPI

To upload your package to PyPI, use Twine:
```bash
twine upload dist/*
```
You'll be prompted for your PyPI username & password.

## Release on conda-forge (only admins)

Every time you create a new release on PyPI, an automatic PR is opened on the ewccli [conda-forge feedstock](https://github.com/conda-forge/ewccli-feedstock). Once tests pass and PR is merged, a new release will be created on conda-forge automatically in few seconds. Check [README](https://github.com/conda-forge/ewccli-feedstock#updating-ewccli-feedstock) in the feedstock.

## Update the ewccli skill

The `ewccli` skill in the [eumetsat/skills](https://github.com/eumetsat/skills/tree/main/skills) repository documents the CLI for AI assistants. After each release, check whether the new version changed anything user-facing (commands, options, defaults, workflows) and, if so, open a PR against `skills/skills/ewccli` in that repository to keep the skill in sync with the released version.

## Update Community Hub Item

The `ewccli` hub item in the [ewcloud/ewc-community-hub](https://github.com/ewcloud/ewc-community-hub) catalog lists the supported `ewccli` versions. After each release, open a PR in that repository to bump the item's `version` field to the new release so users installing the EWCCLI know about the updated version.


## Share news in EWC Rocketchat

Advertise the release on the [EWC Rocket.Chat](https://chat.europeanweather.cloud/) (e.g. in the EWC CLI / Community Hub channel):

- Announce the new version and highlight the new features and fixes (pull the highlights from the [CHANGELOG.md](./CHANGELOG.md) for that release).
- Mention how to get it: `pip install --upgrade ewccli` (or `conda update conda-forge::ewccli`).
- Remind users to share feedback and report issues: open an issue on [ewcloud/ewccli/issues](https://github.com/ewcloud/ewccli/issues) or contact the EWC Support Portal.
