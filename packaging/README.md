# Debian packaging

`packaging/build.py` builds the tracked `skills/ppt-master/` tree as an
`axion-ppt-master` Debian package inside a fixed package-builder Docker image.
The host requires Python 3, Docker, and a complete Git worktree. The container
provides Git, `dpkg`, and `dpkg-deb`; the package does not install presentation
runtime dependencies.

The package declares a Debian dependency on `axion-bootstrap`. Package managers
such as APT must install and configure it before configuring `axion-ppt-master`.

```bash
python3 packaging/build.py
python3 packaging/build.py --arch amd64
python3 packaging/build.py --arch arm64 -V 0.2.0 -beta 4 \
  -o /tmp/axion-ppt-master_arm64.deb
```

The target architecture maps to these fixed images:

- `amd64`: `axion-registry.cn-beijing.cr.aliyuncs.com/axion/package-builder:1.3.0-ubuntu22.04-amd64`
- `arm64`: `axion-registry.cn-beijing.cr.aliyuncs.com/axion/package-builder:1.3.0-debian12-arm64`

`--arch` defaults to the current machine architecture and accepts `amd64` or
`arm64`. The package version defaults to `packaging/VERSION`; `-V/--version`
overrides it. `-beta/--beta NUMBER` appends `~beta.NUMBER`; for example,
`-V 1.2.3 -beta 4` produces version `1.2.3~beta.4`. The beta number must be a
non-negative integer. The default output is
`packaging/dist/axion-ppt-master_<version>_<arch>.deb`. `-o/--output` selects an
explicit Deb file, including a path outside the repository.

Only files tracked by Git below `skills/ppt-master/` enter the package. Local
`.env` files, caches, generated projects, and other untracked files are excluded.
The package installs the skill under `/opt/axion/skills/ppt-master` and expects
the target system to provide `glenclaw:glenclaw` with UID/GID `10001:10001`.

Inspect a result with:

```bash
dpkg-deb -f packaging/dist/axion-ppt-master_1.0.0_arm64.deb \
  Package Version Architecture Depends Installed-Size
dpkg-deb -c packaging/dist/axion-ppt-master_1.0.0_arm64.deb
```

## Continuous delivery

`.github/workflows/package.yml` runs on pushes to `main`, `develop`, and exact
case-insensitive `vX.Y.Z` release tags. It executes three sequential jobs:

1. validate repository attribution and compile the shipped Python tools;
2. calculate the Git-derived version, build an arm64 Deb, and retain it as a
   workflow artifact for 14 days;
3. publish `main` packages to the Aptly `test` repository and `develop`
   packages to `develop`. Tag packages remain workflow artifacts only.

An exact release tag builds `X.Y.Z`. An untagged branch commit after the nearest
reachable release tag builds the next patch as `X.Y.(Z+1)~beta.N`, where `N` is
the number of commits after that tag. With no reachable release tag, the base is
`0.0.1` and `N` is the total commit count. The self-hosted runner must provide
Docker and `axion-aptly-publish`.
