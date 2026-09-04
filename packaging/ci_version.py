#!/usr/bin/env python3
"""
PPT Master - CI Debian Version Resolver

Resolve GitHub Actions Debian version and Aptly publication metadata.

Usage:
    GITHUB_REF=refs/heads/main python3 packaging/ci_version.py

Examples:
    GITHUB_REF=refs/heads/main python3 packaging/ci_version.py
    GITHUB_REF=refs/tags/v1.0.0 python3 packaging/ci_version.py

Dependencies:
    Git and the Python standard library
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RELEASE_TAG_PATTERN = re.compile(
    r"v([0-9]+)\.([0-9]+)\.([0-9]+)",
    flags=re.IGNORECASE,
)
BRANCH_REPOSITORIES = {"main": "test", "develop": "develop"}
TAG_REPOSITORIES = ("stable", "test", "develop")
GitOutput = Callable[[list[str]], str]


@dataclass(frozen=True)
class CIVersion:
    """Describe one CI package version and its publication channels."""

    base_version: str
    beta_number: int | None
    deb_version: str
    publish_repositories: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the CI version resolver argument parser."""

    return argparse.ArgumentParser(
        description="Resolve GitHub Actions Debian package metadata.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def git_output(command: list[str]) -> str:
    """Run one read-only Git metadata command and return trimmed stdout."""

    completed = subprocess.run(
        ["git", *command],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def parse_release_tag(tag: str) -> tuple[int, int, int] | None:
    """Parse one exact case-insensitive vX.Y.Z release tag."""

    match = RELEASE_TAG_PATTERN.fullmatch(tag.strip())
    if match is None:
        return None
    return tuple(int(match.group(index)) for index in range(1, 4))


def format_release(version: tuple[int, int, int]) -> str:
    """Format a numeric release tuple as X.Y.Z."""

    return ".".join(str(component) for component in version)


def exact_release_at_head(git: GitOutput = git_output) -> tuple[int, int, int] | None:
    """Return the unique release version tagged exactly at HEAD."""

    releases = {
        release
        for tag in git(["tag", "--points-at", "HEAD"]).splitlines()
        if (release := parse_release_tag(tag)) is not None
    }
    if len(releases) > 1:
        values = ", ".join(format_release(release) for release in sorted(releases))
        raise ValueError(f"HEAD has multiple release versions: {values}")
    return next(iter(releases)) if releases else None


def closest_reachable_release(
    git: GitOutput = git_output,
) -> tuple[tuple[int, int, int], int] | None:
    """Return the closest reachable release, preferring the highest tied version."""

    candidates: list[tuple[int, tuple[int, int, int]]] = []
    for tag in git(["tag", "--merged", "HEAD"]).splitlines():
        release = parse_release_tag(tag)
        if release is None:
            continue
        distance = int(git(["rev-list", "--count", f"{tag}..HEAD"]))
        candidates.append((distance, release))

    if not candidates:
        return None
    closest_distance = min(distance for distance, _ in candidates)
    closest_release = max(
        release for distance, release in candidates if distance == closest_distance
    )
    return closest_release, closest_distance


def ref_kind(github_ref: str) -> tuple[str, str]:
    """Validate one supported GitHub ref and return its kind and short name."""

    if github_ref.startswith("refs/heads/"):
        branch = github_ref.removeprefix("refs/heads/")
        if branch in BRANCH_REPOSITORIES:
            return "branch", branch
    if github_ref.startswith("refs/tags/"):
        tag = github_ref.removeprefix("refs/tags/")
        if parse_release_tag(tag) is not None:
            return "tag", tag
    raise ValueError(
        "CI ref must be main, develop, or an exact case-insensitive vX.Y.Z tag: "
        f"{github_ref!r}"
    )


def resolve_ci_version(
    github_ref: str,
    git: GitOutput = git_output,
) -> CIVersion:
    """Resolve the package version and publication channels for one CI ref."""

    kind, name = ref_kind(github_ref)
    exact_release = exact_release_at_head(git)
    if exact_release is not None:
        if kind == "tag" and parse_release_tag(name) != exact_release:
            raise ValueError(f"tag ref {name!r} does not match the release at HEAD")
        version = format_release(exact_release)
        repositories = TAG_REPOSITORIES if kind == "tag" else ()
        return CIVersion(version, None, version, repositories)
    if kind == "tag":
        raise ValueError(f"tag ref {name!r} does not point at an exact release tag")

    previous = closest_reachable_release(git)
    if previous is None:
        release = (0, 0, 1)
        beta_number = int(git(["rev-list", "--count", "HEAD"]))
    else:
        previous_release, beta_number = previous
        release = (
            previous_release[0],
            previous_release[1],
            previous_release[2] + 1,
        )
    if beta_number <= 0:
        raise ValueError("an untagged branch build must be after its release baseline")

    base_version = format_release(release)
    return CIVersion(
        base_version,
        beta_number,
        f"{base_version}~beta.{beta_number}",
        (BRANCH_REPOSITORIES[name],),
    )


def main(argv: list[str] | None = None) -> int:
    """Print validated values in GitHub Actions output-file syntax."""

    build_parser().parse_args(argv)
    github_ref = os.environ.get("GITHUB_REF", "").strip()
    version = resolve_ci_version(github_ref)
    print(f"base_version={version.base_version}")
    print(f"beta_number={'' if version.beta_number is None else version.beta_number}")
    print(f"deb_version={version.deb_version}")
    print(f"publish_repositories={','.join(version.publish_repositories)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"CI version resolution failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
