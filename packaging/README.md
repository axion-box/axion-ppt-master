# Debian packaging

`packaging/build.py` builds the tracked `skills/ppt-master/` tree as an
`axion-ppt-master` Debian package. It requires Python 3, Git, `dpkg`, and
`dpkg-deb`; it does not install presentation runtime dependencies.

```bash
python3 packaging/build.py
python3 packaging/build.py --version 0.2.0 --arch amd64
python3 packaging/build.py --version 0.2.0 --arch arm64 --beta \
  --output-dir /tmp/ppt-master-debs
```

The defaults are read from `packaging/VERSION`, use the `arm64` architecture,
and write to the repository `dist/` directory. `--beta` appends `~beta`, so the
example above produces `axion-ppt-master_0.2.0~beta_arm64.deb`.

Only files tracked by Git below `skills/ppt-master/` enter the package. Local
`.env` files, caches, generated projects, and other untracked files are excluded.
The package installs the skill under `/opt/axion/skills/ppt-master` and expects
the target system to provide `glenclaw:glenclaw` with UID/GID `10001:10001`.

Inspect a result with:

```bash
dpkg-deb -f dist/axion-ppt-master_0.1.1_arm64.deb \
  Package Version Architecture Installed-Size
dpkg-deb -c dist/axion-ppt-master_0.1.1_arm64.deb
```
