#!/usr/bin/env python3

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    source_dir = repo_root / "skills" / "ppt-master"
    target_root = Path.home() / ".axion-agent" / "skills"
    target_dir = target_root / "ppt-master"

    if not source_dir.is_dir():
        print(f"Source skill directory not found: {source_dir}", file=sys.stderr)
        return 1

    target_root.mkdir(parents=True, exist_ok=True)

    if target_dir.exists():
        shutil.rmtree(target_dir)

    shutil.copytree(source_dir, target_dir)
    print(f"Installed {source_dir} -> {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
