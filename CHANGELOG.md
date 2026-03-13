# Changelog

All notable changes to this project are documented in this file.

# 0.3.0

### Features

- feat: Introduce experimental deployment of item developed locally, not on public github yet ([#57](https://github.com/ewcloud/ewccli/pull/57)) ([216a50a](https://github.com/ewcloud/ewccli/commit/216a50a297f08e3d274d2e019a9add8fb9dfac97))
- feat: Allow interaction with custom local catalogue for testing non published items ([#52](https://github.com/ewcloud/ewccli/pull/52)) ([ef20420](https://github.com/ewcloud/ewccli/commit/ef204201510079ae7767f693d693b2a0df96a449))
- feat: Introduce profiles for multiple clouds ([#46](https://github.com/ewcloud/ewccli/pull/46)) ([5e94702](https://github.com/ewcloud/ewccli/commit/5e947022dba1af813c757e3c221291487d69c2d4))
- feat: update images list ([#41](https://github.com/ewcloud/ewccli/pull/41)) ([43d2f53](https://github.com/ewcloud/ewccli/commit/43d2f53a7656dde9e095db232201550514ae3d0e))
- feat: Introduce ewc version command ([#40](https://github.com/ewcloud/ewccli/pull/40)) ([cc162af](https://github.com/ewcloud/ewccli/commit/cc162afc3d114eabaa4faf63350490e9ec0b47e4))
- feat: Introduce --force flag for ewc hub list command ([#39](https://github.com/ewcloud/ewccli/pull/39)) ([64a198a](https://github.com/ewcloud/ewccli/commit/64a198aa4f3def5260a02e820573d06b0265103a))


### Bug Fixes

- fix: fix hub list ([#87](https://github.com/ewcloud/ewccli/pull/87)) ([4bd497f](https://github.com/ewcloud/ewccli/commit/4bd497fd8fa4e08f64967db161aa4218062384a6))
- fix: configuration mismatch not returning correct value for flavor ([#86](https://github.com/ewcloud/ewccli/pull/86)) ([6d72964](https://github.com/ewcloud/ewccli/commit/6d729642c4d913de58649383289646c5677e4b00))
- fix: variable not in context ([#85](https://github.com/ewcloud/ewccli/pull/85)) ([b087b42](https://github.com/ewcloud/ewccli/commit/b087b4276dee4c1e7b85a5338e26d1e5a21ab013))
- fix: existing ssh keys should not be overwritten ([#83](https://github.com/ewcloud/ewccli/pull/83)) ([e45db42](https://github.com/ewcloud/ewccli/commit/e45db42662fcc89065e572ba33d348323562d33c))
- fix: default image retrieval ([#70](https://github.com/ewcloud/ewccli/pull/70)) ([a779ffe](https://github.com/ewcloud/ewccli/commit/a779ffe97cea13e8f195da7f7a36a626c8c1aa81))
- fix: cli should recognize empty known item-inputs passed ([#63](https://github.com/ewcloud/ewccli/pull/63)) ([8b26cbd](https://github.com/ewcloud/ewccli/commit/8b26cbdccfab850edab6e4ed15f84fd95bd61a66))
- fix: add missing default mandatory value ([#50](https://github.com/ewcloud/ewccli/pull/50)) ([a523850](https://github.com/ewcloud/ewccli/commit/a523850fb3a29fa8a618523b83dd2f91e61e49aa))
- fix: Respect image name input precedence over default from items file ([#49](https://github.com/ewcloud/ewccli/pull/49)) ([0f9e1b5](https://github.com/ewcloud/ewccli/commit/0f9e1b5c2f7ec057aa4341483be7f0db04a4f934))
- fix: use federee not region for federated clouds ([#43](https://github.com/ewcloud/ewccli/pull/43)) ([fe32f34](https://github.com/ewcloud/ewccli/commit/fe32f341ef0c28c4e9005d72c375a4755b145821))


# 0.2.1

### Bug Fixes

- Fix error on the check on external IP ([#34]https://github.com/ewcloud/ewccli/pull/34) [0d4ac0e](https://github.com/ewcloud/ewccli/commit/0d4ac0ed176abe0d03c808d3caf9e2f1cab14240)
- DNS check error message and time ([#32]https://github.com/ewcloud/ewccli/pull/32) [43735ef](https://github.com/ewcloud/ewccli/commit/43735ef2d36697d5a26462a6911a3fe0c853a511)

# 0.2.0

### Features

- Use defaultSecurityGroups and checkDNS from items index [b77b43b](https://github.com/ewcloud/ewccli/commit/b77b43b3916438e476606b58b965712bc08a407d)
- Introduce checkDNS for items ([#29](https://github.com/ewcloud/ewccli/pull/29)) [7f98a6a](https://github.com/ewcloud/ewccli/commit/7f98a6ab9dcb96825f259663aac8445daaee1b1d)
- bump versions ([#26](https://github.com/ewcloud/ewccli/pull/26)) [78adb02](https://github.com/ewcloud/ewccli/commit/78adb024771c7a3bc8da83c1325c51a171259557)

### Bug Fixes
- Set DNS check to 15 minutes [9f24e2f](https://github.com/ewcloud/ewccli/commit/9f24e2f5a7584db980eb0863fc9ab57521536151)
- ewc hub list command item name should show all name always ([#25](https://github.com/ewcloud/ewccli/pull/25)) [e4869fc](https://github.com/ewcloud/ewccli/commit/e4869fcd4757910160ec68894417fae76ca622b5)


# 0.1.1 (2025-10-08)

### Bug Fixes

* Force ansible roles download when new versions exist ([#22](https://github.com/ewcloud/ewccli/pull/22)) ([#3](https://github.com/ewcloud/ewccli/issues/3)) ([9263391](https://github.com/ewcloud/ewccli/commit/92633917a71d3cf5cf6aea23f4fef83e052f3f92))
* Remove dependency not used ([#19](https://github.com/ewcloud/ewccli/pull/19)) ([#6](https://github.com/ewcloud/ewccli/issues/6)) ([d44135b](https://github.com/ewcloud/ewccli/commit/d44135bbaf8864722dc324f201d0ad4f61c5a89d))

# 0.1.0 (2025-09-12)

In this initial release, basic funcionality for ewc login, ewc hub and ewc infra command groups have been released. This is also the first release on GitHub with all public code.

### Features

* code for v0.1.0 [4c425d5](https://github.com/ewcloud/ewccli/commit/4c425d57e0d24a64161c8faddb59643107547625)
* initial files [6321a7e](https://github.com/ewcloud/ewccli/commit/6321a7e8b42e68e0b19042f42382e8ad030f469a)
