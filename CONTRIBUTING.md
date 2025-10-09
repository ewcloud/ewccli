# How to Contribute

This project is [licensed](./LICENSE) and accepts contributions via GitHub pull
requests. In this document, we outline some of the conventions on development
workflow, commit message formatting, contact points and other resources to make
it easier to get your contribution accepted.

## Getting Started

* Fork the repository on GitHub.
* Read the [README.md](./README.md) for usage/test instructions.
* Play with the project, submit bugs or patches.

### Contribution Flow

On the contributors' side:
1. Create a topic branch from the main brach to base your work on.
2. Make commits of logical units (checkout
[commit guidelines](#commit-guidelines) below).
3. Push changes to a topic branch in your fork of the repository.
4. Make sure to validate changes by running tests on a
EWC environment.
5. Submit a pull request to this repository, including details on
the steps necessary to reproduce your tests; assign maintainers for
review/approval.

On the maintainers' side:

1. Review, validate/test internally, and provide feedback prior to porting the
changes into a topic branch in the private upstream of this GitHub repository.
2. Upon approval, squash-merge changes in the upstream, making sure to leave
only one conventional commit as result from the merge; include full
acknowledgement of the contributors (i.e. list their GitHub handles) in the
body of the commit message.
3. Update the [CHANGELOG.md](./CHANGELOG.md), commit-tag it
to the main branch and mirror into GitHub.
4. Mark the relevant GitHub issue is as resolved.

### Commit Guidelines

This repository enforces
[conventional commits](https://www.conventionalcommits.org/en/v1.0.0/)
to mark breaking, major and minor code changes in accordance with the
[Semantic Versioning](https://semver.org/) standard:
- Commits that are merged to the main branch should always be prefixed by
specific keyword (i.e. `docs`, `style`, `feat`, `fix`, `refactor`, `ci`,
`chore` or `test`)
- Value is communicated to the end-users by three of the prefixes:
  - `fix:` Patches a bug in your codebase.
  - `feat:` Introduces a new feature to the codebase.
  - `BREAKING CHANGE:` Introduces a breaking API change. A
`BREAKING CHANGE` can be part of commits of any type.

## Reporting Security Vulnerabilities

Due to their public nature, GitHub and RocketChat are not appropriate places
for reporting vulnerabilities. If you suspect you have found a security
vulnerability, please do not file a GitHub issue, but instead email
[support@europeanweather.cloud](mailto:support@europeanweather.cloud) with the
full details, including steps to reproduce the issue.
