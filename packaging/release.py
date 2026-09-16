#!/usr/bin/env python3
"""Build, verify, and publish axion-ppt-master Deb and TGZ releases."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


PACKAGE_NAME = "axion-ppt-master"
RELEASE_REPOSITORIES = ("stable", "test", "develop")
DEFAULT_APT_ROOT = Path("/srv/axion/apt")
TARBALL_PREFIX = "tarball/v1/channels"
DEFAULT_OSS_BUCKET = "axion-deb"
DEFAULT_OSS_ENDPOINT = "oss-cn-beijing.aliyuncs.com"
DEFAULT_OSSUTIL_IMAGE = (
    "axion-registry.cn-beijing.cr.aliyuncs.com/axion/ossutil:1.7.19"
)


def command_output(args: list[str], *, cwd: Path | None = None) -> str:
    """Run one command and return trimmed stdout."""

    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def sha256_file(path: Path) -> str:
    """Stream the SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def deb_metadata(path: Path) -> dict[str, str]:
    """Read the identity fields from one Deb."""

    output = command_output(
        ["dpkg-deb", "-f", str(path), "Package", "Version", "Architecture"]
    )
    fields: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def package_records(index: Path) -> list[dict[str, str]]:
    """Parse an Apt Packages index."""

    if not index.is_file():
        raise ValueError(f"Packages index is missing: {index}")
    records: list[dict[str, str]] = []
    stanza: dict[str, str] = {}
    for line in index.read_text(encoding="utf-8").splitlines() + [""]:
        if not line:
            if stanza:
                records.append(stanza)
            stanza = {}
            continue
        if line.startswith((" ", "\t")):
            continue
        key, separator, value = line.partition(":")
        if separator:
            stanza[key] = value.strip()
    return records


def _release_environment(path: Path) -> dict[str, str]:
    """Load the runner-owned release environment without logging secrets."""

    if not path.is_file():
        raise ValueError(f"runner release environment is missing: {path}")
    completed = subprocess.run(
        ["bash", "-c", 'set -a; . "$1"; env -0', "bash", str(path)],
        check=True,
        stdout=subprocess.PIPE,
    )
    values: dict[str, str] = {}
    for item in completed.stdout.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        values[key.decode()] = value.decode()
    for key in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET"):
        if not values.get(key):
            raise ValueError(f"runner release environment lacks {key}: {path}")
    return values


class OssClient:
    """Minimal pinned-ossutil wrapper for the tarball namespace."""

    def __init__(self, environment: dict[str, str], workspace: Path):
        self.environment = {**os.environ, **environment}
        self.workspace = workspace.resolve()
        self.endpoint = environment.get("TARBALL_OSS_ENDPOINT", DEFAULT_OSS_ENDPOINT)
        self.bucket = environment.get("TARBALL_OSS_BUCKET", DEFAULT_OSS_BUCKET)
        self.image = environment.get("OSSUTIL_IMAGE", DEFAULT_OSSUTIL_IMAGE)

    def _run(
        self, arguments: list[str], *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            "-e",
            "OSS_ACCESS_KEY_ID",
            "-e",
            "OSS_ACCESS_KEY_SECRET",
            "-e",
            "OSS_ENDPOINT",
            "-v",
            f"{self.workspace}:/work",
            self.image,
            "-c",
            'set -eu; ossutil config -e "$OSS_ENDPOINT" -i "$OSS_ACCESS_KEY_ID" '
            '-k "$OSS_ACCESS_KEY_SECRET" -L EN -c /tmp/ossutilconfig >/dev/null; '
            'exec ossutil "$@" -c /tmp/ossutilconfig',
            "ossutil",
            *arguments,
        ]
        return subprocess.run(
            command,
            check=check,
            env={**self.environment, "OSS_ENDPOINT": self.endpoint},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def target(self, key: str) -> str:
        """Return the full OSS URL for one object key."""

        return f"oss://{self.bucket}/{key}"

    @staticmethod
    def _output(result: subprocess.CompletedProcess[str]) -> str:
        return "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )

    @classmethod
    def _missing(cls, result: subprocess.CompletedProcess[str]) -> bool:
        output = cls._output(result).casefold()
        return (
            any(marker in output for marker in ("nosuchkey", "objectnotexist"))
            or re.search(r"\b404\b", output) is not None
        )

    def exists(self, key: str) -> bool:
        """Return whether an OSS object exists."""

        result = self._run(["stat", self.target(key)], check=False)
        if result.returncode == 0:
            return True
        if self._missing(result):
            return False
        raise RuntimeError(f"ossutil stat failed for {key}: {self._output(result)}")

    def download(self, key: str, destination: Path) -> bool:
        """Download an object into the bound workspace if it exists."""

        destination = destination.resolve()
        if destination.parent != self.workspace:
            raise ValueError(f"OSS download escapes workspace: {destination}")
        result = self._run(
            ["cp", self.target(key), f"/work/{destination.name}", "-f"],
            check=False,
        )
        if result.returncode == 0:
            return True
        if self._missing(result):
            return False
        raise RuntimeError(f"ossutil download failed for {key}: {self._output(result)}")

    def upload(self, source: Path, key: str) -> None:
        """Upload one workspace file."""

        source = source.resolve()
        if source.parent != self.workspace:
            raise ValueError(f"OSS upload escapes workspace: {source}")
        result = self._run(
            ["cp", f"/work/{source.name}", self.target(key), "-f"], check=False
        )
        if result.returncode != 0:
            raise RuntimeError(f"ossutil upload failed for {key}: {self._output(result)}")


@contextlib.contextmanager
def _channel_lock(apt_root: Path):
    """Serialize package-local channel read-modify-write operations."""

    lock_path = apt_root / ".tarball-v1-channel.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        if os.name == "posix":
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def _write_version_files(
    directory: Path, *, tarball: Path, version: str, architecture: str
) -> tuple[Path, Path, str]:
    """Write the checksum and metadata sidecars for one TGZ."""

    digest = sha256_file(tarball)
    stem = f"{PACKAGE_NAME}_{version}"
    checksum = directory / f"{stem}.checksum"
    metadata = directory / f"{stem}.json"
    checksum.write_text(
        f"{digest}  {tarball.name}\n", encoding="utf-8", newline="\n"
    )
    metadata.write_text(
        json.dumps(
            {
                "package": PACKAGE_NAME,
                "arch": architecture,
                "version": version,
                "filename": tarball.name,
                "sha256": digest,
                "size": tarball.stat().st_size,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return checksum, metadata, digest


def _ensure_small_immutable(client: OssClient, source: Path, key: str) -> None:
    """Upload an immutable sidecar or verify its existing bytes."""

    existing = source.with_name(source.name + ".remote")
    if client.download(key, existing):
        if existing.read_bytes() != source.read_bytes():
            raise ValueError(f"immutable OSS object differs: {key}")
        return
    client.upload(source, key)


def _merge_channel(path: Path, version: str) -> None:
    """Put one version first in a minimal channel index."""

    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if set(value) != {"versions"} or not isinstance(value["versions"], list):
            raise ValueError(f"invalid tarball channel index: {path}")
        versions = value["versions"]
        if not all(isinstance(item, str) and item for item in versions):
            raise ValueError(f"invalid versions in tarball channel index: {path}")
    else:
        versions = []
    path.write_text(
        json.dumps(
            {"versions": [version, *(item for item in versions if item != version)]},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def publish_tarball(
    *,
    tarball: Path,
    version: str,
    architecture: str,
    channels: tuple[str, ...],
    apt_root: Path,
) -> None:
    """Publish one TGZ and update only its package-local channel indexes."""

    if channels not in (("test",), ("develop",), RELEASE_REPOSITORIES):
        raise ValueError(f"unsupported tarball channels: {channels!r}")
    expected_name = f"{PACKAGE_NAME}_{version}.tgz"
    if not tarball.is_file() or tarball.stat().st_size == 0:
        raise ValueError(f"tarball is missing or empty: {tarball}")
    if tarball.name != expected_name:
        raise ValueError(f"unexpected tarball filename: {tarball.name}")

    environment = _release_environment(apt_root / channels[0] / ".env")
    with tempfile.TemporaryDirectory(prefix=f"{PACKAGE_NAME}-publish-") as raw:
        workspace = Path(raw)
        local_tarball = workspace / tarball.name
        try:
            os.link(tarball, local_tarball)
        except OSError:
            shutil.copyfile(tarball, local_tarball)
        checksum, metadata, digest = _write_version_files(
            workspace,
            tarball=local_tarball,
            version=version,
            architecture=architecture,
        )
        client = OssClient(environment, workspace)
        version_root = f"{TARBALL_PREFIX}/{PACKAGE_NAME}/{architecture}/{version}"
        _ensure_small_immutable(client, checksum, f"{version_root}/{checksum.name}")
        _ensure_small_immutable(client, metadata, f"{version_root}/{metadata.name}")
        tarball_key = f"{version_root}/{local_tarball.name}"
        if not client.exists(tarball_key):
            client.upload(local_tarball, tarball_key)
        print(f"PPT Master TGZ SHA256: {digest}", flush=True)

        with _channel_lock(apt_root):
            for channel in channels:
                key = (
                    f"{TARBALL_PREFIX}/{PACKAGE_NAME}/{architecture}/"
                    f"channels/{channel}.json"
                )
                path = workspace / f"channel-{channel}.json"
                client.download(key, path)
                _merge_channel(path, version)
                client.upload(path, key)


def fetch_published_tarball(
    *,
    destination: Path,
    version: str,
    architecture: str,
    channels: tuple[str, ...],
    apt_root: Path,
) -> Path | None:
    """Fetch and verify an already-published TGZ for retry reuse."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    environment = _release_environment(apt_root / channels[0] / ".env")
    client = OssClient(environment, destination.parent)
    version_root = f"{TARBALL_PREFIX}/{PACKAGE_NAME}/{architecture}/{version}"
    checksum = destination.with_suffix(".checksum.remote")
    checksum_key = f"{version_root}/{PACKAGE_NAME}_{version}.checksum"
    if not client.download(checksum_key, checksum):
        if client.exists(f"{version_root}/{destination.name}"):
            raise ValueError(f"published TGZ lacks checksum sidecar: {version_root}")
        return None
    match = re.fullmatch(
        r"([0-9a-f]{64})  (\S+)", checksum.read_text(encoding="utf-8").strip()
    )
    if match is None or match.group(2) != destination.name:
        raise ValueError(f"invalid published TGZ checksum: {checksum_key}")
    if not client.download(f"{version_root}/{destination.name}", destination):
        return None
    if sha256_file(destination) != match.group(1):
        raise ValueError(f"published TGZ checksum differs: {destination}")
    return destination


def published_release(
    apt_root: Path,
    version: str,
    architecture: str,
    repositories: tuple[str, ...],
) -> tuple[Path | None, set[str]]:
    """Locate a byte-identical Deb already present in requested repositories."""

    package: Path | None = None
    checksum: str | None = None
    present: set[str] = set()
    for repository in repositories:
        public = (apt_root / repository / "data/public").resolve()
        index = public / f"dists/bookworm/main/binary-{architecture}/Packages"
        for record in package_records(index):
            identity = (
                record.get("Package"),
                record.get("Version"),
                record.get("Architecture"),
            )
            if identity != (PACKAGE_NAME, version, architecture):
                continue
            digest = record.get("SHA256", "")
            filename = record.get("Filename", "")
            if not re.fullmatch(r"[0-9a-f]{64}", digest) or not filename:
                raise ValueError(f"published package lacks Filename/SHA256: {index}")
            candidate = (public / filename).resolve()
            if not candidate.is_relative_to(public):
                raise ValueError(f"published package path escapes repository: {candidate}")
            if not candidate.is_file() or sha256_file(candidate) != digest:
                raise ValueError(f"published package is missing or differs: {candidate}")
            if checksum is not None and checksum != digest:
                raise ValueError(f"release {version} differs across repositories")
            checksum = digest
            package = candidate
            present.add(repository)
    return package, present


def build_package(
    *,
    repository_root: Path,
    tarball_version: str,
    debian_version: str,
    architecture: str,
) -> tuple[Path, Path]:
    """Build both release artifacts from a clean checkout."""

    commit = command_output(["git", "rev-parse", "HEAD"], cwd=repository_root)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"invalid source commit: {commit!r}")
    if command_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=repository_root,
    ):
        raise ValueError("PPT Master checkout must be clean before release build")
    output = repository_root / "packaging" / "dist" / "ci"
    deb = output / f"{PACKAGE_NAME}_{debian_version}_{architecture}.deb"
    tarball = output / f"{PACKAGE_NAME}_{tarball_version}.tgz"
    subprocess.run(
        [
            sys.executable,
            str(repository_root / "packaging" / "build.py"),
            "--arch",
            architecture,
            "--version",
            debian_version,
            "--tarball-version",
            tarball_version,
            "--output",
            str(deb),
            "--tgz-output",
            str(tarball),
        ],
        cwd=repository_root,
        check=True,
    )
    return deb, tarball


def build_and_publish(
    *,
    repository_root: Path,
    tarball_version: str,
    debian_version: str,
    repositories: tuple[str, ...],
    architecture: str,
    apt_root: Path = DEFAULT_APT_ROOT,
) -> Path:
    """Build or reuse immutable artifacts and publish requested channels."""

    if repositories not in (("test",), ("develop",), RELEASE_REPOSITORIES):
        raise ValueError(f"unsupported repositories: {repositories!r}")
    if architecture != "arm64":
        raise ValueError("the production runner currently publishes arm64 only")
    if debian_version != tarball_version.replace("-beta.", "~beta."):
        raise ValueError("Deb and TGZ versions disagree")
    if repositories == RELEASE_REPOSITORIES and "-beta." in tarball_version:
        raise ValueError("stable publication requires an exact release version")

    package, present = published_release(
        apt_root, debian_version, architecture, repositories
    )
    tarball: Path | None = None
    if package is not None:
        tarball = fetch_published_tarball(
            destination=(
                repository_root
                / "packaging"
                / "dist"
                / "ci"
                / f"{PACKAGE_NAME}_{tarball_version}.tgz"
            ),
            version=tarball_version,
            architecture=architecture,
            channels=repositories,
            apt_root=apt_root,
        )
    if package is None or tarball is None:
        built_package, tarball = build_package(
            repository_root=repository_root,
            tarball_version=tarball_version,
            debian_version=debian_version,
            architecture=architecture,
        )
        if package is not None and sha256_file(package) != sha256_file(built_package):
            raise ValueError(f"rebuilt release {debian_version} differs from published Deb")
        package = built_package
    else:
        print(f"reuse published PPT Master Deb and TGZ: {package}", flush=True)

    expected = {
        "Package": PACKAGE_NAME,
        "Version": debian_version,
        "Architecture": architecture,
    }
    if deb_metadata(package) != expected:
        raise RuntimeError(f"Deb identity mismatch: expected {expected}")
    print(f"PPT Master Deb SHA256: {sha256_file(package)}", flush=True)
    for repository in repositories:
        if repository in present:
            print(f"{repository} already contains the identical Deb", flush=True)
            continue
        subprocess.run(
            ["axion-aptly-publish", "publish", "--repo", repository, str(package)],
            check=True,
        )
    publish_tarball(
        tarball=tarball,
        version=tarball_version,
        architecture=architecture,
        channels=repositories,
        apt_root=apt_root,
    )
    return package


def main(argv: list[str] | None = None) -> int:
    """Run the release publisher."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--tarball-version", required=True)
    parser.add_argument("--debian-version", required=True)
    parser.add_argument("--repositories", required=True)
    parser.add_argument("--architecture", default="arm64")
    parser.add_argument("--apt-root", type=Path, default=DEFAULT_APT_ROOT)
    args = parser.parse_args(argv)
    build_and_publish(
        repository_root=args.repository_root.resolve(),
        tarball_version=args.tarball_version,
        debian_version=args.debian_version,
        repositories=tuple(args.repositories.split(",")),
        architecture=args.architecture,
        apt_root=args.apt_root,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"PPT Master release failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
