# Releasing ewccli

## Prepare changelog and tag

### 0. Pull latest main and create new branch
```bash
git checkout main
git pull
git checkout -b release/vX.Y.Z
```

### 1. Prepare the version bump

Update the version in:

- `pyproject.toml`
- `ewccli/__init__.py`

### 2. Run the full test suite (it will be run also in the PR but anyway)
```bash
pytest
```

### 3. Update the CHANGELOG
Generate the list of commits since the last tag and update the `CHANGELOG.md` file using vim or similar. (You can use for example `git log $(git describe --tags --abbrev=0)..HEAD --pretty=format:"- %s (%h)" > CHANGELOG_UNRELEASED.md` to generate the list of commits and PR used also)
```
### Bug Fixes
* Force ansible roles download when new versions exist ([#22](https://github.com/ewcloud/ewccli/pull/22)) ([#3](https://github.com/ewcloud/ewccli/issues/3)) ([9263391](https://github.com/ewcloud/ewccli/commit/92633917a71d3cf5cf6aea23f4fef83e052f3f92))
* Remove dependency not used ([#19](https://github.com/ewcloud/ewccli/pull/19)) ([#6](https://github.com/ewcloud/ewccli/issues/6)) ([d44135b](https://github.com/ewcloud/ewccli/commit/d44135bbaf8864722dc324f201d0ad4f61c5a89d))
```

### 4. Commit the release changes
```bash
git add CHANGELOG.md pyproject.toml ewccli/__init__.py
git commit --cleanup=whitespace -m "chore: release X.Y.Z"
```

```
chore: 0.2.0 [skip ci]

# [0.2.0](https://github.com/ewcloud/ewccli/compare/0.1.1...0.2.0) (2025-10-14)

### Features

- feat: Use defaultSecurityGroups and checkDNS from items index [b77b43b](https://github.com/ewcloud/ewccli/commit/b77b43b3916438e476606b58b965712bc08a407d)
- feat: Introduce checkDNS for items ([#29](https://github.com/ewcloud/ewccli/pull/29)) [7f98a6a](https://github.com/ewcloud/ewccli/commit/7f98a6ab9dcb96825f259663aac8445daaee1b1d)
- feat: bump versions ([#26](https://github.com/ewcloud/ewccli/pull/26)) [78adb02](https://github.com/ewcloud/ewccli/commit/78adb024771c7a3bc8da83c1325c51a171259557)

### Bug Fixes
- fix: Set DNS check to 15 minutes [9f24e2f](https://github.com/ewcloud/ewccli/commit/9f24e2f5a7584db980eb0863fc9ab57521536151)
- fix: ewc hub list command item name should show all name always ([#25](https://github.com/ewcloud/ewccli/pull/25)) [e4869fc](https://github.com/ewcloud/ewccli/commit/e4869fcd4757910160ec68894417fae76ca622b5)
```

### 5. Open a Pull Request titled: `Release X.Y.Z`and Request review from a colleague.
Push your branch:

```bash
git push -u origin release/vX.Y.Z

```

### 6. Once approved and CI pass, merge the PR.

### 7. Pull the updated main locally and create a tag with the new version number, eg:

   ```
   git tag -a <X.Y.Z> -m "Version <X.Y.Z>"
   ```

   For example if the previous tag was `0.1.1` and the new release is a
   patch release, do:

   ```
   git tag -a 0.1.1 -m "Version 0.1.1"
   ```

   See [semver.org](http://semver.org/) on how to write a version number.

### 8. Push tags to GitHub `git push --follow-tags`

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

## Release on conda-forge (only admins) NOT AVAILABLE YET, SKIP FOR NOW.

Once release is on PyPI, you can create the change on conda-forge (only admins) https://www.pyopensci.org/python-package-guide/tutorials/publish-conda-forge.html#

Step 1: Install grayskull

```bash
pip install grayskull
```

Step 2: Fork and clone the conda-forge staged-recipes repository

```bash
git clone git@github.com:conda-forge/staged-recipes.git
```

Step 3: Create your conda-forge recipe

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

recipes/packagename/meta.yaml

Step 3b: Bug fix - add a home url to the about: section

There is currently a small bug in Grayskull where it doesn’t populate the home: element of the recipe. If you don’t include this, you will receive an error message from the friendly conda-forge linter bot.

Step 4: tests for conda-forge

If you need to

Step 4: Submit a pull request to the staged-recipes repository
