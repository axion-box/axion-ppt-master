#!/usr/bin/env bash

set -euo pipefail

target_dir=/usr/local/axion/skills/ppt-master
uninstaller_dir=/usr/local/.uninstallers/axion-ppt-master

rm -rf -- "${target_dir}"
rm -f -- "${uninstaller_dir}/uninstall.sh"
rmdir -- "${uninstaller_dir}" 2>/dev/null || true
