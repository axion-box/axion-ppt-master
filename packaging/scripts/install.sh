#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source_dir="${script_dir}/payload/usr/local/axion/skills/ppt-master"
target_parent=/usr/local/axion/skills
target_dir="${target_parent}/ppt-master"
uninstaller_dir=/usr/local/.uninstallers/axion-ppt-master

test "${EUID}" -eq 0

if [[ -f "${uninstaller_dir}/uninstall.sh" ]]; then
  bash "${uninstaller_dir}/uninstall.sh"
fi
bash "${script_dir}/uninstall.sh"

install -d -m 0755 /usr/local/axion "${target_parent}"
cp -a "${source_dir}" "${target_dir}"
chown -R 10001:10001 "${target_dir}"
install -D -m 0755 "${script_dir}/uninstall.sh" "${uninstaller_dir}/uninstall.sh"

printf 'installed axion-ppt-master into %s; reboot to activate it\n' "${target_dir}"
