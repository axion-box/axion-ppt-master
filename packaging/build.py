#!/usr/bin/env python3
"""
PPT Master - Debian Package Builder

Build the tracked PPT Master skill files into an axion-ppt-master Deb package.

Usage:
    python3 packaging/build.py [--arch ARCH] [-o OUTPUT] [-V VERSION] [--beta NUMBER]

Examples:
    python3 packaging/build.py
    python3 packaging/build.py -V 0.2.0 --arch amd64 -beta 4
    python3 packaging/build.py -o /tmp/axion-ppt-master.deb

Dependencies:
    Host: Docker
    Container: git, dpkg, and dpkg-deb
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import shutil
import stat
import subprocess
import sys
import tempfile


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE_ROOT = PROJECT_ROOT / "packaging"
SKILL_ROOT = PROJECT_ROOT / "skills" / "ppt-master"
VERSION_FILE = PACKAGE_ROOT / "VERSION"
POSTINST_FILE = PACKAGE_ROOT / "scripts" / "postinst"
PACKAGE_NAME = "axion-ppt-master"
DIST_ROOT = PACKAGE_ROOT / "dist"
SKILL_REPOSITORY_PREFIX = "skills/ppt-master/"
CONTAINER_BUILD_ENV = "AXION_PACKAGING_CONTAINER_BUILD"
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
    """Create the Debian package builder argument parser."""

    parser = argparse.ArgumentParser(
        description="Build the tracked PPT Master skill as a Debian package.",
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
        "-V",
        "--version",
        help="Debian package version; defaults to packaging/VERSION.",
    )
    parser.add_argument(
        "-beta",
        "--beta",
        type=_parse_beta_number,
        metavar="NUMBER",
        help="Append ~beta.NUMBER to the package version.",
    )
    return parser


def _parse_beta_number(value: str) -> int:
    """Parse one non-negative beta sequence number."""

    if not value.isdigit():
        raise argparse.ArgumentTypeError("beta number must be a non-negative integer")
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
        raise BuildError(
            "missing required command(s): "
            + ", ".join(missing)
            + "; install the Debian dpkg tools and Git"
        )


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

    if requested != "auto":
        return _normalize_arch(requested)
    return _normalize_arch(platform.machine())


def _builder_image(arch: str) -> str:
    """Return the fixed package-builder image for one Debian architecture."""

    try:
        tag = BUILDER_IMAGE_TAGS[arch]
    except KeyError as error:
        raise BuildError(f"unsupported architecture: {arch}") from error
    return f"{BUILDER_IMAGE_REPOSITORY}:{tag}"


def _resolve_output_path(
    requested: pathlib.Path | None,
    *,
    arch: str,
    version: str,
) -> pathlib.Path:
    """Resolve the requested Deb path or use the standard dist filename."""

    if requested is None:
        return DIST_ROOT / f"{PACKAGE_NAME}_{version}_{arch}.deb"

    output = requested.expanduser()
    if not output.is_absolute():
        output = pathlib.Path.cwd() / output
    output = output.absolute()
    if output.suffix != ".deb":
        raise BuildError("-o/--output must name a .deb file")
    return output


def _docker_build_command(args: argparse.Namespace, *, arch: str) -> list[str]:
    """Build the Docker command that re-enters this script in the builder."""

    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        f"linux/{arch}",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        f"{CONTAINER_BUILD_ENV}=1",
        "--env",
        "HOME=/tmp/axion-package-builder-home",
        "--mount",
        f"type=bind,src={PROJECT_ROOT},dst={PROJECT_ROOT}",
        "--workdir",
        str(PROJECT_ROOT),
    ]

    output: pathlib.Path | None = None
    if args.output is not None:
        output = _resolve_output_path(
            args.output,
            arch=arch,
            version="0.0.0",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output_parent = output.parent.resolve()
        if not output_parent.is_relative_to(PROJECT_ROOT):
            command.extend(
                [
                    "--mount",
                    f"type=bind,src={output_parent},dst={output_parent}",
                ]
            )

    command.extend(
        [
            _builder_image(arch),
            "python3",
            "packaging/build.py",
            "--arch",
            arch,
        ]
    )
    if output is not None:
        command.extend(["--output", str(output)])
    if args.version is not None:
        command.extend(["--version", args.version])
    if args.beta is not None:
        command.extend(["--beta", str(args.beta)])
    return command


def _build_with_docker(args: argparse.Namespace, *, arch: str) -> None:
    """Run the package build in the architecture-specific builder image."""

    _run(_docker_build_command(args, arch=arch))


def _read_default_version() -> str:
    """Read the package-owned default version."""

    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise BuildError(f"could not read default version from {VERSION_FILE}: {error}") from error
    if not version:
        raise BuildError(f"default version file is empty: {VERSION_FILE}")
    return version


def _validate_version(version: str) -> str:
    """Validate one non-empty Debian version."""

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
    """Resolve the requested version and apply the optional beta suffix."""

    requested_version = (
        explicit_version if explicit_version is not None else _read_default_version()
    )
    version = _validate_version(requested_version)
    if beta is not None:
        version = _validate_version(f"{version}~beta.{beta}")
    return version


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
        if not separator:
            raise BuildError("git returned an invalid tracked-file entry")
        fields = metadata.split()
        if len(fields) != 3:
            raise BuildError("git returned invalid tracked-file metadata")
        mode = int(fields[0], 8)
        repository_path = pathlib.Path(os.fsdecode(raw_path))
        repository_text = repository_path.as_posix()
        if not repository_text.startswith(SKILL_REPOSITORY_PREFIX):
            raise BuildError(f"tracked path is outside the skill directory: {repository_text}")
        relative_path = pathlib.Path(repository_text.removeprefix(SKILL_REPOSITORY_PREFIX))
        if not relative_path.parts or ".." in relative_path.parts:
            raise BuildError(f"tracked path is unsafe: {repository_text}")
        entries.append((mode, relative_path))
    if not entries:
        raise BuildError(f"no tracked files found under {SKILL_ROOT}")
    return entries


def _copy_payload(destination: pathlib.Path) -> int:
    """Copy tracked skill files into the package root and return their byte size."""

    total_size = 0
    for git_mode, relative_path in _tracked_skill_entries():
        source = SKILL_ROOT / relative_path
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if git_mode == 0o120000:
            target.symlink_to(os.readlink(source))
            continue
        if not source.is_file():
            raise BuildError(f"tracked skill file is missing: {source}")
        shutil.copyfile(source, target)
        target.chmod(0o755 if git_mode & stat.S_IXUSR else 0o644)
        total_size += source.stat().st_size
    return total_size


def _write_control(debian_dir: pathlib.Path, version: str, arch: str, installed_size: int) -> None:
    """Write Debian package metadata and the post-installation script."""

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
    control_file = debian_dir / "control"
    control_file.write_text(control, encoding="utf-8")
    control_file.chmod(0o644)
    shutil.copyfile(POSTINST_FILE, debian_dir / "postinst")
    (debian_dir / "postinst").chmod(0o755)


def _normalize_directory_modes(package_root: pathlib.Path) -> None:
    """Make package directories independent of the build host's umask."""

    package_root.chmod(0o755)
    for current_root, directories, _files in os.walk(package_root):
        pathlib.Path(current_root).chmod(0o755)
        for directory in directories:
            (pathlib.Path(current_root) / directory).chmod(0o755)


def _validate_deb(path: pathlib.Path, version: str, arch: str) -> None:
    """Validate package metadata, payload, and maintainer scripts."""

    expected = {
        "Package": PACKAGE_NAME,
        "Version": version,
        "Architecture": arch,
    }
    for field, expected_value in expected.items():
        actual = _run(["dpkg-deb", "--field", str(path), field], capture=True)
        if actual != expected_value:
            raise BuildError(
                f"built package {field} is {actual!r}, expected {expected_value!r}"
            )
    contents = _run(["dpkg-deb", "--contents", str(path)], capture=True)
    required_path = "./opt/axion/skills/ppt-master/SKILL.md"
    if required_path not in contents:
        raise BuildError(f"built package does not contain {required_path}")
    with tempfile.TemporaryDirectory(prefix="axion-ppt-control-") as temporary:
        control_dir = pathlib.Path(temporary) / "control"
        _run(["dpkg-deb", "--control", str(path), str(control_dir)])
        postinst = control_dir / "postinst"
        if not postinst.is_file() or not os.access(postinst, os.X_OK):
            raise BuildError("built package does not contain an executable postinst")


def build_package(version: str, arch: str, output: pathlib.Path) -> pathlib.Path:
    """Build and validate one axion-ppt-master Deb package."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".build-",
        dir=output.parent,
    ) as temporary:
        temporary_root = pathlib.Path(temporary)
        package_root = temporary_root / "root"
        skill_destination = package_root / "opt" / "axion" / "skills" / "ppt-master"
        payload_bytes = _copy_payload(skill_destination)
        installed_size = max(1, (payload_bytes + 1023) // 1024)
        _write_control(package_root / "DEBIAN", version, arch, installed_size)
        _normalize_directory_modes(package_root)
        candidate = temporary_root / output.name
        print(f"Building {PACKAGE_NAME} {version} for {arch}", file=sys.stderr)
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
        os.replace(candidate, output)
    return output


def main(argv: list[str] | None = None) -> int:
    """Build the requested Deb package and print its path."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        arch = _resolve_arch(args.arch)
        if os.environ.get(CONTAINER_BUILD_ENV) != "1":
            if shutil.which("docker") is None:
                raise BuildError("missing required command: docker")
            _build_with_docker(args, arch=arch)
            return 0

        _require_container_commands()
        version = _resolve_version(args.version, args.beta)
        output = _resolve_output_path(args.output, arch=arch, version=version)
        print(f"package arch: {arch}", file=sys.stderr)
        print(f"package version: {version}", file=sys.stderr)
        print(f"package output: {output}", file=sys.stderr)
        package_path = build_package(version, arch, output)
    except (BuildError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Deb build failed: {error}", file=sys.stderr)
        return 1
    print(package_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
