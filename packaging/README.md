# Axion packaging

`packaging/build.py` stages only the Git-tracked `skills/ppt-master/` tree and
builds both release formats from that same payload:

- `axion-ppt-master_<debian-version>_<arch>.deb`
- `axion-ppt-master_<version>.tgz`

The package remains one repository, one package, and one installed Skill. It
does not discover or bundle other directories below `skills/`.

Both formats install the Skill at
`/usr/local/axion/skills/ppt-master`. The TGZ contains exactly one top-level
versioned directory whose release interface is `install.sh` plus `payload/`.
The installer must run as root, validates the existing `glenclaw:glenclaw`
identity as UID/GID `10001:10001`, replaces only the `ppt-master` directory,
and restores an active `axion-agent.service` after the transaction.

## Local build

The host needs Python 3 and Docker. The build container supplies Git and the
Debian packaging tools.

```bash
python3 packaging/build.py --arch arm64
python3 packaging/build.py --arch arm64 \
  --version 1.0.1~beta.4 \
  --tarball-version 1.0.1-beta.4 \
  --output packaging/dist/axion-ppt-master_1.0.1~beta.4_arm64.deb \
  --tgz-output packaging/dist/axion-ppt-master_1.0.1-beta.4.tgz
```

The target architecture maps to these fixed images:

- `amd64`: `axion-registry.cn-beijing.cr.aliyuncs.com/axion/package-builder:1.3.0-ubuntu22.04-amd64`
- `arm64`: `axion-registry.cn-beijing.cr.aliyuncs.com/axion/package-builder:1.3.0-debian12-arm64`

## Continuous delivery

`.github/workflows/package.yml` runs one release job on `main`, `develop`, and
exact `vX.Y.Z` tags. Untagged `main` commits publish to `test`, untagged
`develop` commits publish to `develop`, and exact release tags publish the same
artifacts to `stable`, `test`, and `develop`. Branch workflows skip commits
already carrying a release tag.

The self-hosted Hong Kong runner builds and publishes the Deb through Aptly,
then writes the TGZ directly to the Beijing `axion-deb` bucket. GitHub workflow
artifacts and release assets are not used.

Version objects follow this immutable layout:

```text
tarball/v1/channels/axion-ppt-master/<arch>/<version>/axion-ppt-master_<version>.tgz
tarball/v1/channels/axion-ppt-master/<arch>/<version>/axion-ppt-master_<version>.checksum
tarball/v1/channels/axion-ppt-master/<arch>/<version>/axion-ppt-master_<version>.json
```

Each package-local channel index is stored at:

```text
tarball/v1/channels/axion-ppt-master/<arch>/channels/<channel>.json
```

Its complete schema is:

```json
{"versions":["1.0.1-beta.4"]}
```
