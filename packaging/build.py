#!/usr/bin/env python3
"""Build axion-ppt-master Deb and installer TGZ artifacts from one payload."""

from __future__ import annotations

import argparse
import gzip
import os
import pathlib
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE_ROOT = PROJECT_ROOT / "packaging"
SKILL_ROOT = PROJECT_ROOT / "skills" / "ppt-master"
VERSION_FILE = PACKAGE_ROOT / "VERSION"
POSTINST_FILE = PACKAGE_ROOT / "scripts" / "postinst"
INSTALL_SCRIPT = PACKAGE_ROOT / "scripts" / "install.sh"
PACKAGE_NAME = "axion-ppt-master"
DIST_ROOT = PACKAGE_ROOT / "dist"
INSTALL_ROOT = pathlib.PurePosixPath("/usr/local/axion/skills/ppt-master")
SKILL_REPOSITORY_PREFIX = "skills/ppt-master/"
CONTAINER_BUILD_ENV = "AXION_PACKAGING_CONTAINER_BUILD"
HOST_OUTPUT_ENV = "AXION_PACKAGING_HOST_OUTPUT_DIR"
BUILDER_IMAGE_REPOSITORY = (
    "axion-registry.cn-beijing.cr.aliyuncs.com/axion/package-builder"
)
BUILDER_IMAGE_TAGS = {
    "amd64": "1.3.0-ubuntu22.04-amd64",
    "arm64": "1.3.0-debian12-arm64",
}


class BuildError(RuntimeError):
    """Report one actionable package-build failure."""


def build_parser() -> argparse.ArgumentParser:
    """Create the package builder argument parser."""

    parser = argparse.ArgumentParser(
        description="Build axion-ppt-master Deb and TGZ artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--arch",
        choices=("auto", "amd64", "arm64"),
        default="auto",
        help="Target architecture; defaults to the current machine architecture.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        help="Deb output file; defaults to packaging/dist/<name>_<version>_<arch>.deb.",
    )
    parser.add_argument(
        "--tgz-output",
        type=pathlib.Path,
        help="TGZ output file; defaults beside the Deb output.",
    )
    parser.add_argument(
        "-V",
        "--version",
        help="Debian package version; defaults to packaging/VERSION.",
    )
    parser.add_argument(
        "--beta",
        type=_parse_beta_number,
        metavar="NUMBER",
        help="Append ~beta.NUMBER to the Debian version.",
    )
    parser.add_argument(
        "--tarball-version",
        help="Filename-safe version for the TGZ; inferred from the Debian version.",
    )
    return parser


def _parse_beta_number(value: str) -> int:
    """Parse one positive beta sequence number."""

    if not value.isdigit() or int(value) <= 0:
        raise argparse.ArgumentTypeError("beta number must be a positive integer")
    return int(value)


def _run(command: list[str], *, capture: bool = False) -> str:
    """Run one checked command from the repository root."""

    print("+ " + " ".join(command), file=sys.stderr, flush=True)
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return completed.stdout.strip() if completed.stdout is not None else ""


def _require_container_commands() -> None:
    """Require every external tool used inside the builder container."""

    missing = [name for name in ("git", "dpkg", "dpkg-deb") if shutil.which(name) is None]
    if missing:
        raise BuildError("missing required command(s): " + ", ".join(missing))


def _normalize_arch(raw: str) -> str:
    """Normalize machine architecture names to Debian architecture names."""

    value = raw.strip().lower()
    if value in {"amd64", "x86_64"}:
        return "amd64"
    if value in {"arm64", "aarch64"}:
        return "arm64"
    raise BuildError(f"unsupported architecture: {raw}")


def _resolve_arch(requested: str) -> str:
    """Resolve an explicit target architecture or use the host architecture."""

    return _normalize_arch(platform.machine() if requested == "auto" else requested)


def _builder_image(arch: str) -> str:
    """Return the fixed package-builder image for one architecture."""

    try:
        tag = BUILDER_IMAGE_TAGS[arch]
    except KeyError as error:
        raise BuildError(f"unsupported architecture: {arch}") from error
    return f"{BUILDER_IMAGE_REPOSITORY}:{tag}"


def _absolute_output(requested: pathlib.Path) -> pathlib.Path:
    """Resolve one caller-selected output path."""

    output = requested.expanduser()
    if not output.is_absolute():
        output = pathlib.Path.cwd() / output
    return output.absolute()


def _resolve_output_path(
    requested: pathlib.Path | None,
    *,
    arch: str,
    version: str,
) -> pathlib.Path:
    """Resolve the Deb path."""

    output = (
        DIST_ROOT / f"{PACKAGE_NAME}_{version}_{arch}.deb"
        if requested is None
        else _absolute_output(requested)
    )
    if output.suffix != ".deb":
        raise BuildError("-o/--output must name a .deb file")
    return output


def _resolve_tarball_version(requested: str | None, debian_version: str) -> str:
    """Resolve the filename-safe TGZ version."""

    value = (
        requested.strip()
        if requested is not None
        else debian_version.replace("~beta.", "-beta.")
    )
    pattern = r"[0-9]+\.[0-9]+\.[0-9]+(?:-beta\.[1-9][0-9]*)?"
    if re.fullmatch(pattern, value) is None:
        raise BuildError(f"unsupported tarball version: {value!r}")
    return value


def _resolve_tgz_output_path(
    requested: pathlib.Path | None,
    *,
    deb_output: pathlib.Path,
    tarball_version: str,
) -> pathlib.Path:
    """Resolve the TGZ path and keep both outputs on one filesystem."""

    output = (
        deb_output.parent / f"{PACKAGE_NAME}_{tarball_version}.tgz"
        if requested is None
        else _absolute_output(requested)
    )
    if output.suffix != ".tgz":
        raise BuildError("--tgz-output must name a .tgz file")
    if output.parent != deb_output.parent:
        raise BuildError("Deb and TGZ outputs must use the same directory")
    return output


def _docker_build_command(
    args: argparse.Namespace,
    *,
    arch: str,
) -> list[str]:
    """Build the Docker command that re-enters this script."""

    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        f"linux/{arch}",
        "--env",
        f"{CONTAINER_BUILD_ENV}=1",
        "--env",
        "HOME=/tmp/axion-package-builder-home",
        "--env",
        "GIT_CONFIG_COUNT=1",
        "--env",
        "GIT_CONFIG_KEY_0=safe.directory",
        "--env",
        f"GIT_CONFIG_VALUE_0={PROJECT_ROOT}",
        "--mount",
        f"type=bind,src={PROJECT_ROOT},dst={PROJECT_ROOT},readonly",
        "--workdir",
        str(PROJECT_ROOT),
    ]

    output_parent: pathlib.Path | None = None
    if args.output is not None:
        output_parent = _absolute_output(args.output).parent
    if args.tgz_output is not None:
        tgz_parent = _absolute_output(args.tgz_output).parent
        if output_parent is not None and tgz_parent != output_parent:
            raise BuildError("Deb and TGZ outputs must use the same directory")
        output_parent = tgz_parent
    if output_parent is not None:
        output_parent.mkdir(parents=True, exist_ok=True)
        command.extend(
            [
                "--env",
                f"{HOST_OUTPUT_ENV}={output_parent}",
                "--mount",
                f"type=bind,src={output_parent},dst=/output",
            ]
        )

    command.extend([_builder_image(arch), "python3", "packaging/build.py", "--arch", arch])
    if args.output is not None:
        command.extend(["--output", f"/output/{_absolute_output(args.output).name}"])
    if args.tgz_output is not None:
        command.extend(
            ["--tgz-output", f"/output/{_absolute_output(args.tgz_output).name}"]
        )
    if args.version is not None:
        command.extend(["--version", args.version])
    if args.beta is not None:
        command.extend(["--beta", str(args.beta)])
    if args.tarball_version is not None:
        command.extend(["--tarball-version", args.tarball_version])
    return command


def _read_default_version() -> str:
    """Read the package-owned default version."""

    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise BuildError(f"could not read default version: {error}") from error
    if not version:
        raise BuildError(f"default version file is empty: {VERSION_FILE}")
    return version


def _validate_version(version: str) -> str:
    """Validate one Debian version."""

    value = version.strip()
    if not value:
        raise BuildError("package version must not be empty")
    completed = subprocess.run(
        ["dpkg", "--validate-version", value],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "invalid Debian version"
        raise BuildError(f"invalid package version {value!r}: {detail}")
    return value


def _resolve_version(explicit_version: str | None, beta: int | None) -> str:
    """Resolve the requested Debian version."""

    version = _validate_version(
        explicit_version if explicit_version is not None else _read_default_version()
    )
    return _validate_version(f"{version}~beta.{beta}") if beta is not None else version


def _tracked_skill_entries() -> list[tuple[int, pathlib.Path]]:
    """List tracked skill paths with their Git file modes."""

    output = subprocess.run(
        ["git", "ls-files", "-z", "--stage", "--", "skills/ppt-master"],
        cwd=PROJECT_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    entries: list[tuple[int, pathlib.Path]] = []
    for raw_entry in output.split(b"\0"):
        if not raw_entry:
            continue
        metadata, separator, raw_path = raw_entry.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise BuildError("git returned invalid tracked-file metadata")
        mode = int(fields[0], 8)
        repository_path = pathlib.Path(os.fsdecode(raw_path))
        repository_text = repository_path.as_posix()
        if not repository_text.startswith(SKILL_REPOSITORY_PREFIX):
            raise BuildError(f"tracked path is outside the skill: {repository_text}")
        relative = pathlib.Path(repository_text.removeprefix(SKILL_REPOSITORY_PREFIX))
        if not relative.parts or ".." in relative.parts:
            raise BuildError(f"tracked path is unsafe: {repository_text}")
        if mode == 0o120000:
            raise BuildError(f"symlinks are forbidden in the package: {repository_text}")
        entries.append((mode, relative))
    if not entries:
        raise BuildError(f"no tracked files found under {SKILL_ROOT}")
    return entries


def _stage_payload(payload_root: pathlib.Path) -> int:
    """Copy the tracked skill into the canonical installation payload."""

    destination = payload_root / INSTALL_ROOT.relative_to("/")
    total_size = 0
    for git_mode, relative in _tracked_skill_entries():
        source = SKILL_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not source.is_file():
            raise BuildError(f"tracked skill file is missing: {source}")
        shutil.copyfile(source, target)
        target.chmod(0o755 if git_mode & stat.S_IXUSR else 0o644)
        total_size += source.stat().st_size
    return total_size


def _write_control(
    debian_dir: pathlib.Path,
    version: str,
    arch: str,
    installed_size: int,
) -> None:
    """Write Debian metadata and the post-installation script."""

    control = (
        f"Package: {PACKAGE_NAME}\n"
        f"Version: {version}\n"
        "Section: utils\n"
        "Priority: optional\n"
        f"Architecture: {arch}\n"
        "Maintainer: Axion Team\n"
        f"Installed-Size: {installed_size}\n"
        "Homepage: https://github.com/axion-box/axion-ppt-master\n"
        "Description: Axion PPT master skill package.\n"
    )
    debian_dir.mkdir(parents=True, exist_ok=True)
    (debian_dir / "control").write_text(control, encoding="utf-8", newline="\n")
    shutil.copyfile(POSTINST_FILE, debian_dir / "postinst")
    (debian_dir / "postinst").chmod(0o755)


def _copy_payload_tree(source: pathlib.Path, destination: pathlib.Path) -> None:
    """Clone the canonical payload using hard links where possible."""

    shutil.copytree(source, destination, copy_function=os.link)


def _normalize_directory_modes(root: pathlib.Path) -> None:
    """Make payload directories independent of the build host umask."""

    root.chmod(0o755)
    for current_root, directories, _files in os.walk(root):
        pathlib.Path(current_root).chmod(0o755)
        for directory in directories:
            (pathlib.Path(current_root) / directory).chmod(0o755)


def _validate_deb(path: pathlib.Path, version: str, arch: str) -> None:
    """Validate Deb identity and the required installation path."""

    for field, expected in {
        "Package": PACKAGE_NAME,
        "Version": version,
        "Architecture": arch,
    }.items():
        actual = _run(["dpkg-deb", "--field", str(path), field], capture=True)
        if actual != expected:
            raise BuildError(f"built package {field} is {actual!r}, expected {expected!r}")
    contents = _run(["dpkg-deb", "--contents", str(path)], capture=True)
    required = f".{INSTALL_ROOT}/SKILL.md"
    if required not in contents:
        raise BuildError(f"built package does not contain {required}")


def _build_deb(
    workspace: pathlib.Path,
    payload_root: pathlib.Path,
    target: pathlib.Path,
    version: str,
    arch: str,
    installed_size: int,
) -> pathlib.Path:
    """Build a Deb from the canonical payload."""

    package_root = workspace / "deb-root"
    _copy_payload_tree(payload_root, package_root)
    _write_control(package_root / "DEBIAN", version, arch, installed_size)
    _normalize_directory_modes(package_root)
    candidate = workspace / target.name
    _run(
        [
            "dpkg-deb",
            "--build",
            "--root-owner-group",
            str(package_root),
            str(candidate),
        ]
    )
    _validate_deb(candidate, version, arch)
    return candidate


def _build_tarball(
    workspace: pathlib.Path,
    payload_root: pathlib.Path,
    target: pathlib.Path,
    tarball_version: str,
) -> pathlib.Path:
    """Build a deterministic installer TGZ from the canonical payload."""

    if not INSTALL_SCRIPT.is_file():
        raise BuildError(f"tarball installer is missing: {INSTALL_SCRIPT}")
    archive_root = workspace / f"{PACKAGE_NAME}_{tarball_version}"
    archive_root.mkdir()
    installer = archive_root / "install.sh"
    shutil.copyfile(INSTALL_SCRIPT, installer)
    installer.chmod(0o755)
    _copy_payload_tree(payload_root, archive_root / "payload")
    _normalize_directory_modes(archive_root)

    candidate = workspace / target.name
    with candidate.open("wb") as raw:
        with gzip.GzipFile(
            fileobj=raw,
            mode="wb",
            filename="",
            mtime=0,
            compresslevel=9,
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in [archive_root, *sorted(archive_root.rglob("*"))]:
                    current = path.lstat()
                    if stat.S_ISLNK(current.st_mode):
                        raise BuildError(f"symlink is forbidden in TGZ: {path}")
                    info = archive.gettarinfo(
                        str(path), arcname=path.relative_to(workspace).as_posix()
                    )
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = 0
                    if path.is_file():
                        with path.open("rb") as source:
                            archive.addfile(info, source)
                    else:
                        archive.addfile(info)
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise BuildError(f"TGZ build produced an empty artifact: {candidate}")
    return candidate


def _display_path(path: pathlib.Path) -> pathlib.Path:
    """Map a container output path back to the caller-visible path."""

    host_output = os.environ.get(HOST_OUTPUT_ENV)
    return pathlib.Path(host_output) / path.name if host_output else path


def build_artifacts(
    version: str,
    tarball_version: str,
    arch: str,
    deb_output: pathlib.Path,
    tgz_output: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Build and atomically place one Deb and one TGZ."""

    deb_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{PACKAGE_NAME}-build-", dir=deb_output.parent
    ) as temporary:
        workspace = pathlib.Path(temporary)
        payload_root = workspace / "payload"
        payload_bytes = _stage_payload(payload_root)
        installed_size = max(1, (payload_bytes + 1023) // 1024)
        deb_candidate = _build_deb(
            workspace,
            payload_root,
            deb_output,
            version,
            arch,
            installed_size,
        )
        tgz_candidate = _build_tarball(
            workspace, payload_root, tgz_output, tarball_version
        )
        os.replace(deb_candidate, deb_output)
        os.replace(tgz_candidate, tgz_output)
    return deb_output, tgz_output


def main(argv: list[str] | None = None) -> int:
    """Build the requested artifacts."""

    args = build_parser().parse_args(argv)
    try:
        arch = _resolve_arch(args.arch)
        if os.environ.get(CONTAINER_BUILD_ENV) != "1":
            if shutil.which("docker") is None:
                raise BuildError("missing required command: docker")
            _run(_docker_build_command(args, arch=arch))
            return 0

        _require_container_commands()
        version = _resolve_version(args.version, args.beta)
        tarball_version = _resolve_tarball_version(args.tarball_version, version)
        deb_output = _resolve_output_path(args.output, arch=arch, version=version)
        tgz_output = _resolve_tgz_output_path(
            args.tgz_output,
            deb_output=deb_output,
            tarball_version=tarball_version,
        )
        print(f"package arch: {arch}", file=sys.stderr)
        print(f"package version: {version}", file=sys.stderr)
        print(f"tarball version: {tarball_version}", file=sys.stderr)
        deb, tgz = build_artifacts(
            version, tarball_version, arch, deb_output, tgz_output
        )
    except (BuildError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"package build failed: {error}", file=sys.stderr)
        return 1
    print(_display_path(deb))
    print(_display_path(tgz))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
