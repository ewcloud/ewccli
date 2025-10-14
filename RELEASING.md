# Releasing ewccli

0. Make sure the code references the correct new version you want in the pyproject.yaml and in the __init__.py
1. checkout main branch: `git checkout main`
2. pull from repo: `git pull`
3. run the unittests with pytest.
4. Update the `CHANGELOG.md` file using vim or similar. (You can use `git log $(git describe --tags --abbrev=0)..HEAD --pretty=format:"- %s (%h)" > CHANGELOG_UNRELEASED.md` to generate the list of commits and PR used also)
```
### Bug Fixes
* Force ansible roles download when new versions exist ([#22](https://github.com/ewcloud/ewccli/pull/22)) ([#3](https://github.com/ewcloud/ewccli/issues/3)) ([9263391](https://github.com/ewcloud/ewccli/commit/92633917a71d3cf5cf6aea23f4fef83e052f3f92))
* Remove dependency not used ([#19](https://github.com/ewcloud/ewccli/pull/19)) ([#6](https://github.com/ewcloud/ewccli/issues/6)) ([d44135b](https://github.com/ewcloud/ewccli/commit/d44135bbaf8864722dc324f201d0ad4f61c5a89d))
```
5. git add CHANGELOG.md
6. git commit --cleanup=whitespace # commit title and body to be added. Example below:
```
chore: 0.2.0 [skip ci]

# [0.2.0](https://github.com/ewcloud/ewc-flavours/compare/0.1.1...0.2.0) (2025-10-14)

### Features

- feat: Use defaultSecurityGroups and checkDNS from items index [b77b43b](https://github.com/ewcloud/ewccli/commit/b77b43b3916438e476606b58b965712bc08a407d)
- feat: Introduce checkDNS for items ([#29](https://github.com/ewcloud/ewccli/pull/29)) [7f98a6a](https://github.com/ewcloud/ewccli/commit/7f98a6ab9dcb96825f259663aac8445daaee1b1d)
- feat: bump versions ([#26](https://github.com/ewcloud/ewccli/pull/26)) [78adb02](https://github.com/ewcloud/ewccli/commit/78adb024771c7a3bc8da83c1325c51a171259557)

### Bug Fixes
- fix: Set DNS check to 15 minutes [9f24e2f](https://github.com/ewcloud/ewccli/commit/9f24e2f5a7584db980eb0863fc9ab57521536151)
- fix: ewc hub list command item name should show all name always ([#25](https://github.com/ewcloud/ewccli/pull/25)) [e4869fc](https://github.com/ewcloud/ewccli/commit/e4869fcd4757910160ec68894417fae76ca622b5)
```
7. Create a tag with the new version number, eg:

   ```
   git tag -a <new version> -m "Version <new version>"
   ```

   For example if the previous tag was `0.1.1` and the new release is a
   patch release, do:

   ```
   git tag -a 0.1.1 -m "Version 0.1.1"
   ```

   See [semver.org](http://semver.org/) on how to write a version number.

8. Push commits `git push`
9. Push tags to github `git push --follow-tags`
10. Verify github action unittests passed.
11. Create a "Release" on GitHub by going to
   https://github.com/eumetsat/MetopDatasets.jl/releases and clicking "Draft a new release".
   On the next page enter the newly created tag in the "Tag version" field,
   "Version X.Y.Z" in the "Release title" field, and paste the markdown from
   the changelog (the portion under the version section header) in the
   "Describe this release" box. Finally click "Publish release".

12. Now you can start the process to release on PyPI (only admins)

12.1 Build package

Now generate the distribution. To build the package, use PyPA build.

1. Install the build tool
```bash
pip install -q build
```

```bash
python3 -m build
```

you will end up with a `/dist` file. The .whl file and .tar.gz can then be distributed and installed or pushed to PyPI.

9.2 Push package to PyPI

Install twine
```bash
pip install twine
```

If you want to test first, use TestPyPI:
```bash
twine upload --repository testpypi dist/*
```

To upload your package to PyPI, use Twine:
```bash
twine upload dist/*
```
You'll be prompted for your PyPI username & password.

10. Once release is on PyPI, you can create the change on conda-forge (only admins) https://www.pyopensci.org/python-package-guide/tutorials/publish-conda-forge.html#

Step 1: Install grayskull
```bash
pip install grayskull
```

Step 2: Fork and clone the conda-forge staged-recipes repository
```
git clone git@github.com:conda-forge/staged-recipes.git
```


Step 3: Create your conda-forge recipe

```
cd staged-recipes/
```

```
cd examples/
```

```
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
