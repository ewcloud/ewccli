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

> ⛔ As of 06.02.2026, this release stream is not enabled. Skip this section.

Once release is on PyPI, you can create the change on conda-forge (only admins) https://www.pyopensci.org/python-package-guide/tutorials/publish-conda-forge.html#

### 1. Install grayskull

```bash
pip install grayskull
```

### 2. Fork and clone the conda-forge staged-recipes repository

```bash
git clone git@github.com:conda-forge/staged-recipes.git
```

### 3. Create your conda-forge recipe

```bash
cd staged-recipes/
```

```bash
cd examples/
```

```bash
grayskull pypi ewccli
```

When you run grayskull, it will grab the latest distribution of your package from PyPI and will use that to create a new recipe.

The recipe will be saved in a directory named after your package’s name, wherever you run the command.
```
recipes/packagename/meta.yaml
```

#### 3.1. Bug fix - add a home url to the about: section

There is currently a small bug in Grayskull where it doesn’t populate the home: element of the recipe. If you don’t include this, you will receive an error message from the friendly conda-forge linter bot.

### 4. Tests for conda-forge
To ensure packaging was done correctly.

### 5. Submit a pull request to the staged-recipes repository
