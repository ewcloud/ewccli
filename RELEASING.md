# Releasing metoppy

1. checkout main branch
2. pull from repo
3. run the unittests
4. Update the `CHANGELOG.md` file.
5. Create a tag with the new version number, starting with a 'v', eg:

   ```
   git tag -a v<new version> -m "Version <new version>"
   ```

   For example if the previous tag was `v0.9.0` and the new release is a
   patch release, do:

   ```
   git tag -a v0.9.1 -m "Version 0.9.1"
   ```

   See [semver.org](http://semver.org/) on how to write a version number.


6. push changes to github `git push --follow-tags`
7. Verify github action unittests passed.
8. Create a "Release" on GitHub by going to
   https://github.com/eumetsat/MetopDatasets.jl/releases and clicking "Draft a new release".
   On the next page enter the newly created tag in the "Tag version" field,
   "Version X.Y.Z" in the "Release title" field, and paste the markdown from
   the changelog (the portion under the version section header) in the
   "Describe this release" box. Finally click "Publish release".

9. Now you can start the process to release on PyPI, using steps from:
Before 8. look at https://github.com/pytroll/satpy/blob/main/.github/workflows/deploy-sdist.yaml

alternative automation:
9. Verify the GitHub actions for deployment succeed and the release is on PyPI.
If you want to automate this, look at https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
